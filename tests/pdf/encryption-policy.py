#!/usr/bin/env python3
"""opener-0426: encrypted/password-protected PDFs follow fail-closed policy."""

import builtins
from dataclasses import FrozenInstanceError, replace
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from pdf_encryption_policy import (
    MAX_ENCRYPTION_INSPECTION_BYTES,
    PDFEncryptionInspection,
    PDFEncryptionInspectionError,
    PDFEncryptionStatus,
    inspect_pdf_encryption,
)
from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure
from reference_pdf_collection import REFERENCE_PDFS
from scan_results import ScanResultStatus
from unsupported_pdf_features import (
    ENCRYPTED_RESPONSE,
    INCOMPLETE_RESPONSE,
    UnsupportedPDFAction,
)

ROOT = Path(__file__).resolve().parent


def make_pdf(*, user=None, owner=None, use_128bit=True):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    if user is not None:
        writer.encrypt(user_password=user, owner_password=owner, use_128bit=use_128bit)
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class PDFEncryptionPolicyTests(unittest.TestCase):
    def test_real_user_owner_and_empty_user_passwords_all_block(self):
        for label, user, owner, strong in (
            ("user and owner", "fixture-user", "fixture-owner", True),
            ("owner defaults", "fixture-user", None, True),
            ("empty user password", "", "fixture-owner", True),
            ("40-bit encryption", "fixture-user", "fixture-owner", False),
        ):
            with self.subTest(case=label):
                contents = make_pdf(user=user, owner=owner, use_128bit=strong)
                self.assertTrue(PdfReader(BytesIO(contents), strict=True).is_encrypted)
                with patch.object(PdfReader, "decrypt", side_effect=AssertionError("decryption attempted")) as decrypt:
                    result = inspect_pdf_encryption(contents)
                decrypt.assert_not_called()
                self.assertEqual(result.status, PDFEncryptionStatus.ENCRYPTED)
                self.assertIs(result.response, ENCRYPTED_RESPONSE)
                self.assertIs(result.response.scan_status, ScanResultStatus.encrypted)
                self.assertIs(result.response.action, UnsupportedPDFAction.BLOCK)
                self.assertFalse(result.response.permits_open)
                self.assertFalse(result.response.allow_clean_cache)
                self.assertFalse(result.response.allow_destination_handoff)
                self.assertFalse(result.response.allow_fallback)
                self.assertFalse(result.response.allow_override)
                self.assertTrue(result.response.preserve_quarantine)
                self.assertFalse(result.permits_open)
                self.assertNotIn(user or "fixture-owner", result.response.reason)
                with self.assertRaises(PDFStructureParseError) as error:
                    parse_pdf_structure(contents)
                self.assertIn("Encrypted PDF", str(error.exception))
                self.assertNotIn("fixture-user", str(error.exception))
                self.assertNotIn("fixture-owner", str(error.exception))

    def test_unencrypted_documents_are_not_automatically_safe(self):
        for content in (make_pdf(), *(fixture.content for fixture in REFERENCE_PDFS)):
            with self.subTest(length=len(content)):
                result = inspect_pdf_encryption(content)
                self.assertIs(result.status, PDFEncryptionStatus.NOT_ENCRYPTED)
                self.assertIsNone(result.response)
                self.assertFalse(result.permits_open)
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_metadata({"/Subject": "ordinary text /Encrypt is not a trailer entry"})
        output = BytesIO()
        writer.write(output)
        self.assertIs(inspect_pdf_encryption(output.getvalue()).status, PDFEncryptionStatus.NOT_ENCRYPTED)

    def test_malformed_incomplete_or_oversized_inputs_fail_closed(self):
        cases = (None, True, 5, b"", bytearray(make_pdf()),
                 "%PDF-1.4", b"not pdf", b"%PDF-1.4\n%%EOF\n",
                 make_pdf()[:-12], b"x" * (MAX_ENCRYPTION_INSPECTION_BYTES + 1))
        for sample in cases:
            with self.subTest(case=type(sample).__name__, length=len(sample) if hasattr(sample, "__len__") else None):
                with self.assertRaises(PDFEncryptionInspectionError) as error:
                    inspect_pdf_encryption(sample)
                self.assertIs(error.exception.response, INCOMPLETE_RESPONSE)
                self.assertFalse(error.exception.response.permits_open)
                self.assertEqual(str(error.exception), "PDF encryption could not be verified; opening was stopped.")

    def test_missing_parser_and_parsing_failures_are_redacted(self):
        original = builtins.__import__

        def missing(name, *args, **kwargs):
            if name == "pypdf":
                raise ModuleNotFoundError("sensitive file name /private/file.pdf")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=missing):
            with self.assertRaises(PDFEncryptionInspectionError) as error:
                inspect_pdf_encryption(make_pdf())
        self.assertNotIn("sensitive", str(error.exception))
        with patch.object(PdfReader, "is_encrypted", new=property(lambda _: (_ for _ in ()).throw(ValueError("private password")))):
            with self.assertRaises(PDFEncryptionInspectionError) as error:
                inspect_pdf_encryption(make_pdf())
        self.assertNotIn("private password", str(error.exception))

    def test_immutable_policy_evidence_cannot_be_turned_into_permission(self):
        encrypted = inspect_pdf_encryption(make_pdf(user="fixture"))
        with self.assertRaises(FrozenInstanceError):
            encrypted.status = PDFEncryptionStatus.NOT_ENCRYPTED
        with self.assertRaises(ValueError):
            replace(encrypted, permits_open=True)
        with self.assertRaises(ValueError):
            PDFEncryptionInspection(PDFEncryptionStatus.ENCRYPTED, None)
        with self.assertRaises(ValueError):
            PDFEncryptionInspection(PDFEncryptionStatus.NOT_ENCRYPTED, ENCRYPTED_RESPONSE)

    def test_no_scanner_profile_file_io_or_password_prompt_integration(self):
        source = (ROOT / "pdf_encryption_policy.py").read_text(encoding="utf-8")
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        native = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for forbidden in (".decrypt(", "password=", "input(", "getpass", "subprocess", "os.environ",
                          "open(", "write_text(", "launch_clean_file", "remove_quarantine"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("pdf_encryption_policy", gate)
        self.assertNotIn("pdf_encryption_policy", native)
        self.assertIn("--alert-encrypted=yes", gate)
        self.assertIn("python3 test-pdf-encryption-policy.py -v", ci)


if __name__ == "__main__":
    unittest.main()
