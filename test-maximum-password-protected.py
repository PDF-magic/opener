#!/usr/bin/env python3
"""opener-0523: password-protected PDFs must not yield Maximum fidelity copies.

Password protection is an explicit unsupported conversion case. This suite
tests real multi-page encrypted source documents and the actual macOS worker;
it never requests credentials, decrypts source content, or weakens the scanner.
"""

from io import BytesIO
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

import maximum_sanitized_copy as copies


ROOT = Path(__file__).resolve().parent
PASSWORD_CASES = (
    ("rc4_40_user_password", "RC4-40", "synthetic-user-40", "synthetic-owner-40"),
    ("rc4_128_user_password", "RC4-128", "synthetic-user-128", "synthetic-owner-128"),
    ("rc4_128_owner_only", "RC4-128", "", "synthetic-owner-only"),
)


def protected_pdf(algorithm, user_password, owner_password):
    """Create two nonempty, different vector pages before encrypting the PDF."""
    writer = PdfWriter()
    for index in range(2):
        page = writer.add_blank_page(width=180 + index * 20,
                                     height=240 + index * 20)
        stream = DecodedStreamObject()
        stream.set_data((
            f"q {index} 0 1 rg 16 24 {70+index*10} 50 re f Q\n"
        ).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.encrypt(user_password, owner_password, algorithm=algorithm)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def unencrypted_control():
    writer = PdfWriter()
    writer.add_blank_page(width=180, height=240)
    writer.add_blank_page(width=200, height=260)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


class PasswordProtectedDocumentFidelityTests(unittest.TestCase):
    def test_real_encrypted_two_page_fixtures_cover_multiple_password_modes(self):
        samples = []
        for name, algorithm, user, owner in PASSWORD_CASES:
            with self.subTest(case=name):
                source = protected_pdf(algorithm, user, owner)
                self.assertTrue(source.startswith(b"%PDF-"))
                self.assertLess(len(source), copies.MAX_SOURCE_BYTES)
                reader = PdfReader(BytesIO(source), strict=True)
                self.assertTrue(reader.is_encrypted)
                self.assertIsNotNone(reader.trailer.raw_get("/Encrypt"))
                samples.append(source)
        self.assertEqual(len(set(samples)), len(PASSWORD_CASES))

    def test_password_protected_documents_block_all_copy_entrypoints_before_rendering(self):
        converter = Path("/synthetic-optional-converter")
        for name, algorithm, user, owner in PASSWORD_CASES:
            with self.subTest(case=name):
                original = protected_pdf(algorithm, user, owner)
                unchanged = bytes(original)
                with (
                    patch.object(copies, "_trusted_converter", return_value=converter),
                    patch.object(copies, "run_limited_converter") as render,
                    patch.object(PdfReader, "decrypt",
                                 side_effect=AssertionError("never decrypt")) as decrypt,
                    patch("builtins.input", side_effect=AssertionError("no password prompt")) as prompt,
                ):
                    attempt = copies.attempt_sanitized_pdf_copy(original)
                    decision = copies.assess_sanitized_pdf_copy(original)
                    offer = copies.offer_sanitized_pdf_copy(original)
                render.assert_not_called()
                decrypt.assert_not_called()
                prompt.assert_not_called()
                self.assertEqual(original, unchanged)
                self.assertIsNone(offer)
                self.assertIsNone(attempt.offer)
                self.assertIsNotNone(attempt.failure)
                self.assertEqual(
                    attempt.failure.kind,
                    copies.SanitizerFailureKind.UNSUPPORTED_INPUT,
                )
                self.assertEqual(attempt.failure.scan_verdict, "notAssessed")
                self.assertFalse(attempt.failure.permits_open)
                self.assertEqual(decision.action, "block")
                self.assertEqual(
                    decision.blocked_reason,
                    copies.SanitizationBlockReason.encryptedSource,
                )
                self.assertFalse(decision.permits_open)
                self.assertFalse(decision.allow_fallback)
                self.assertFalse(decision.allow_clean_cache)
                self.assertTrue(decision.preserve_quarantine)
                self.assertTrue(decision.requires_separate_scan)
                self.assertFalse(decision.to_dict()["offerAvailable"])
                report = repr(attempt.failure.to_dict()) + repr(decision.to_dict())
                for private in (user, owner):
                    if private:
                        self.assertNotIn(private, report)
                self.assertNotIn("synthetic-optional-converter", report)

    def test_unencrypted_document_reaches_converter_control_without_clean_verdict(self):
        source = unencrypted_control()
        with (
            patch.object(copies, "_trusted_converter",
                         return_value=Path("/synthetic-optional-converter")),
            patch.object(copies, "run_limited_converter",
                         return_value=subprocess.CompletedProcess(
                             [], 0, b"invalid-conversion-result"
                         )) as render,
        ):
            attempt = copies.attempt_sanitized_pdf_copy(source)
        render.assert_called_once()
        self.assertIsNone(attempt.offer)
        self.assertEqual(
            attempt.failure.kind, copies.SanitizerFailureKind.INVALID_OUTPUT
        )
        self.assertFalse(attempt.failure.permits_open)

    def test_installed_scan_gate_preferences_and_mac_ci_remain_independent(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        profiles = (ROOT / "protection_profiles.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/maximum-sanitized-copy.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("test-maximum-password-protected", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("selectable: bool = False", profiles)
        self.assertEqual(
            workflow.count("python3 test-maximum-password-protected.py -v"), 2
        )


@unittest.skipUnless(sys.platform == "darwin",
                     "Actual CoreGraphics converter tests require macOS")
class NativePasswordProtectedDocumentTests(unittest.TestCase):
    def test_real_converter_exits_without_a_copy_for_every_encrypted_document(self):
        converter = ROOT / "maximum-sanitized-copy"
        self.assertTrue(converter.is_file(), "macOS CI must compile the real worker")
        for name, algorithm, user, owner in PASSWORD_CASES:
            with self.subTest(case=name):
                original = protected_pdf(algorithm, user, owner)
                completed = subprocess.run(
                    [str(converter)], input=original, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, timeout=15, check=False,
                )
                self.assertNotEqual(completed.returncode, 0)
                self.assertEqual(completed.stdout, b"")
                self.assertEqual(completed.stderr, b"")
                # No partial, empty, or silently decrypted PDF is exposed.
                self.assertFalse(completed.stdout.startswith(b"%PDF-"))


if __name__ == "__main__":
    unittest.main()
