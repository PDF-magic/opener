#!/usr/bin/env python3
"""opener-1035: validate reusable encrypted PDF security corpus samples."""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from encrypted_pdf_collection import ENCRYPTED_REFERENCE_PDFS
from pdf_encryption_policy import PDFEncryptionStatus, inspect_pdf_encryption
from unsupported_pdf_features import ENCRYPTED_RESPONSE, UnsupportedPDFAction


ROOT = Path(__file__).resolve().parents[2]


class EncryptedCorpusTests(unittest.TestCase):
    def test_encrypted_documents_are_distinct_complete_real_pdfs(self):
        self.assertEqual(
            {item.identifier for item in ENCRYPTED_REFERENCE_PDFS},
            {"user-and-owner-passwords", "empty-user-password", "legacy-40-bit"},
        )
        self.assertEqual(len({item.content for item in ENCRYPTED_REFERENCE_PDFS}), 3)
        self.assertEqual(
            {item.key_bits for item in ENCRYPTED_REFERENCE_PDFS}, {40, 128}
        )
        for item in ENCRYPTED_REFERENCE_PDFS:
            with self.subTest(identifier=item.identifier):
                self.assertTrue(item.content.startswith(b"%PDF-1."))
                self.assertTrue(item.content.rstrip().endswith(b"%%EOF"))
                reader = PdfReader(BytesIO(item.content), strict=True)
                self.assertTrue(reader.is_encrypted)
                # This check verifies that fixtures really contain a page;
                # decryption is confined to the test, never the scanner.
                self.assertTrue(reader.decrypt(item.test_user_password))
                self.assertEqual(len(reader.pages), 1)

    def test_every_encrypted_document_is_blocked_without_decryption(self):
        for item in ENCRYPTED_REFERENCE_PDFS:
            with self.subTest(identifier=item.identifier):
                with patch.object(PdfReader, "decrypt", side_effect=AssertionError(
                        "production inspection must never decrypt")) as decrypt:
                    evidence = inspect_pdf_encryption(item.content)
                decrypt.assert_not_called()
                self.assertIs(evidence.status, PDFEncryptionStatus.ENCRYPTED)
                self.assertIs(evidence.response, ENCRYPTED_RESPONSE)
                self.assertIs(evidence.response.action, UnsupportedPDFAction.BLOCK)
                self.assertFalse(evidence.permits_open)
                self.assertFalse(evidence.response.permits_open)
                self.assertFalse(evidence.response.allow_clean_cache)
                self.assertFalse(evidence.response.allow_destination_handoff)
                self.assertFalse(evidence.response.allow_fallback)
                self.assertFalse(evidence.response.allow_override)
                self.assertTrue(evidence.response.preserve_quarantine)
                if item.test_user_password:
                    self.assertNotIn(item.test_user_password, evidence.response.reason)

    def test_corpus_does_not_change_installed_scanner_or_preferences(self):
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("--alert-encrypted=yes", gate)
        self.assertNotIn("encrypted_pdf_collection", gate)
        self.assertNotIn("pdf_encryption_policy", gate)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/encrypted-documents.py -v", ci)


if __name__ == "__main__":
    unittest.main()
