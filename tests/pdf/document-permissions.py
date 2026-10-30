#!/usr/bin/env python3
"""opener-0461: permission flags and declarations are inspected, not obeyed."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import builtins
import socket
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.generic import (
    ArrayObject, DictionaryObject, NameObject, NumberObject, TextStringObject,
)
from pdf_document_permissions import (
    BLOCK_MESSAGE, PDFDocumentPermissions, PDFDocumentPermissionsError,
    _operations, inspect_pdf_document_permissions,
)
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parents[2]


def make_writer():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    return writer


def serialized(writer):
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def add_signature(writer, *, level=2, key="/DocMDP"):
    ref = writer._add_object(DictionaryObject({
        NameObject("/TransformMethod"): NameObject("/DocMDP"),
        NameObject("/TransformParams"): DictionaryObject({
            NameObject("/P"): NumberObject(level),
        }),
    }))
    signature = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Sig"),
        NameObject("/Reference"): ArrayObject([ref]),
        NameObject("/Reason"): TextStringObject("PRIVATE unverified declaration"),
    }))
    writer._root_object[NameObject("/Perms")] = DictionaryObject({
        NameObject(key): signature,
    })
    return writer


class PDFPermissionTests(unittest.TestCase):
    def assert_blocked(self, data):
        with self.assertRaises(PDFDocumentPermissionsError) as failure:
            inspect_pdf_document_permissions(data)
        self.assertEqual(str(failure.exception), BLOCK_MESSAGE)
        self.assertIsNone(failure.exception.__cause__)

    def test_reference_documents_have_no_declared_permissions(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                record = inspect_pdf_document_permissions(sample.content)
                self.assertEqual(
                    record, PDFDocumentPermissions(False, None, (), True, (), None)
                )
                self.assertFalse(record.authorizes_open)
                self.assertFalse(record.signature_verified)

    def test_standard_encryption_flags_without_password_or_decrypt(self):
        writer = make_writer()
        writer.encrypt(
            "PRIVATE-user-password", "PRIVATE-owner-password",
            permissions_flag=(UserAccessPermissions.PRINT |
                              UserAccessPermissions.EXTRACT),
        )
        with (
            patch.object(PdfReader, "decrypt", side_effect=AssertionError("decrypt attempted")) as decrypt,
            patch.object(socket, "getaddrinfo") as dns,
            patch.object(subprocess, "run") as process,
        ):
            record = inspect_pdf_document_permissions(serialized(writer))
        self.assertTrue(record.is_encrypted)
        self.assertEqual(record.permission_bits & 0xFFFFFFFF, 20)
        self.assertEqual(record.allowed_operations, ("copy", "print"))
        self.assertFalse(record.catalog_inspected)
        self.assertEqual(record.catalog_declarations, ())
        self.assertFalse(record.authorizes_open)
        self.assertNotIn("PRIVATE", repr(record.to_dict()))
        decrypt.assert_not_called()
        dns.assert_not_called()
        process.assert_not_called()
        with self.assertRaises(FrozenInstanceError):
            record.authorizes_open = True

    def test_default_encryption_flags_are_untrusted_evidence(self):
        writer = make_writer()
        writer.encrypt("password", "owner")
        record = inspect_pdf_document_permissions(serialized(writer))
        self.assertIn("print", record.allowed_operations)
        self.assertIn("copy", record.allowed_operations)
        self.assertEqual(record.permission_bits, -4)
        self.assertFalse(record.signature_verified)
        self.assertFalse(record.authorizes_open)

    def test_catalog_certification_and_usage_rights_are_unverified(self):
        record = inspect_pdf_document_permissions(serialized(add_signature(make_writer())))
        self.assertEqual(record.catalog_declarations, ("doc_mdp",))
        self.assertEqual(record.declared_doc_mdp_level, 2)
        self.assertFalse(record.signature_verified)
        self.assertFalse(record.authorizes_open)
        self.assertNotIn("PRIVATE", repr(record))
        self.assertNotIn("PRIVATE", str(record.to_dict()))
        record = inspect_pdf_document_permissions(
            serialized(add_signature(make_writer(), key="/UR3"))
        )
        self.assertEqual(record.catalog_declarations, ("ur3",))
        self.assertIsNone(record.declared_doc_mdp_level)

    def test_bad_catalog_permission_entries_fail_closed(self):
        for level in (0, 4):
            with self.subTest(level=level):
                self.assert_blocked(serialized(add_signature(make_writer(), level=level)))
        writer = make_writer()
        writer._root_object[NameObject("/Perms")] = NumberObject(6)
        self.assert_blocked(serialized(writer))
        writer = make_writer()
        writer._root_object[NameObject("/Perms")] = DictionaryObject({
            NameObject("/DocMDP"): NumberObject(7),
        })
        self.assert_blocked(serialized(writer))

    def test_invalid_permission_bit_ranges_and_result_contract(self):
        for bits in (True, -2**31 - 1, 2**32, "not a permission mask"):
            with self.subTest(bits=bits), self.assertRaises(PDFDocumentPermissionsError):
                _operations(bits)
        for args in (
            (True, None, (), False, (), None),
            (False, 4, (), True, (), None),
            (False, None, ("print",), True, (), None),
            (False, None, (), False, ("doc_mdp",), 1),
            (False, None, (), True, ("doc_mdp",), 5),
            (True, 4, (), True, (), None),
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                PDFDocumentPermissions(*args)

    def test_malformed_encrypted_and_missing_dependency_paths(self):
        for contents in (None, "", b"", b"not-a-pdf", b"%PDF-1.4\n%%EOF",
                         serialized(make_writer())[:-12],
                         b"Z" * (16 * 1024 * 1024 + 1)):
            with self.subTest(kind=type(contents).__name__):
                self.assert_blocked(contents)
        original = builtins.__import__

        def no_parser(name, *args, **kwargs):
            if name == "pypdf" or name.startswith("pypdf."):
                raise ImportError("PRIVATE parser location")
            return original(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=no_parser):
            self.assert_blocked(REFERENCE_PDFS[0].content)

    def test_installed_scan_gate_and_ci_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        source = (ROOT / "pdf_document_permissions.py").read_text(encoding="utf-8")
        self.assertNotIn("pdf_document_permissions", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("python3 tests/pdf/document-permissions.py -v", ci)
        for forbidden in ("decrypt(", "subprocess.", "get_data(", "launch_clean_file(",
                          "remove_quarantine(", "write_text(", "UserDefaults", "os.environ"):
            self.assertNotIn(forbidden, source)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
