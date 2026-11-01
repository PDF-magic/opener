#!/usr/bin/env python3
"""opener-1017: password-protected PDFs under the planned Enhanced profile.

Enhanced is not selectable. Real encrypted PDF fixtures exercise its passive
inspection evidence and fail-closed admission, not an active Enhanced scan.
"""

from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter

from effective_protection_policy import (
    ACTIVE_PROFILE_ID, SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from pdf_encryption_policy import PDFEncryptionStatus, inspect_pdf_encryption
from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure
from protection_policy_definitions import (
    BASELINE_CONTROLS, ControlAvailability, FailureDisposition, PolicyControl,
    PROTECTION_POLICIES,
)
from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
from scan_results import ScanResultStatus
from unsupported_pdf_features import ENCRYPTED_RESPONSE, UnsupportedPDFAction


ROOT = Path(__file__).resolve().parents[2]
CASES = (
    ("user-and-owner-password", "fixture-user", "fixture-owner"),
    ("blank-user-owner-password", "", "fixture-owner-only"),
)


def password_protected_pdf(user_password: str, owner_password: str) -> bytes:
    """Create a valid, actually encrypted PDF without writing user files."""
    writer = PdfWriter()
    writer.add_blank_page(width=240, height=320)
    writer.encrypt(
        user_password=user_password,
        owner_password=owner_password,
        algorithm="RC4-128",
    )
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class EnhancedPasswordProtectedPDFTests(unittest.TestCase):
    def test_real_encrypted_documents_block_without_decryption_or_password_prompt(self):
        for name, user_password, owner_password in CASES:
            with self.subTest(case=name):
                contents = password_protected_pdf(user_password, owner_password)
                self.assertTrue(PdfReader(BytesIO(contents), strict=True).is_encrypted)
                original = bytes(contents)

                with (
                    patch.object(PdfReader, "decrypt",
                                 side_effect=AssertionError("unexpected decryption")) as decrypt,
                    patch("builtins.input",
                          side_effect=AssertionError("unexpected password prompt")) as prompt,
                ):
                    evidence = inspect_pdf_encryption(contents)
                    with self.assertRaises(PDFStructureParseError) as error:
                        parse_pdf_structure(contents)

                decrypt.assert_not_called()
                prompt.assert_not_called()
                self.assertEqual(contents, original)
                self.assertIs(evidence.status, PDFEncryptionStatus.ENCRYPTED)
                self.assertIs(evidence.response, ENCRYPTED_RESPONSE)
                self.assertFalse(evidence.permits_open)
                self.assertIs(evidence.response.action, UnsupportedPDFAction.BLOCK)
                self.assertIs(evidence.response.scan_status, ScanResultStatus.encrypted)
                self.assertFalse(evidence.response.permits_open)
                self.assertFalse(evidence.response.allow_clean_cache)
                self.assertFalse(evidence.response.allow_destination_handoff)
                self.assertFalse(evidence.response.allow_fallback)
                self.assertFalse(evidence.response.allow_override)
                self.assertTrue(evidence.response.preserve_quarantine)
                for credential in (user_password, owner_password):
                    if credential:
                        self.assertNotIn(credential, repr(evidence))
                        self.assertNotIn(credential, str(error.exception))

    def test_enhanced_rejects_selection_without_scanning_or_changing_preferences(self):
        enhanced = PROTECTION_POLICIES[ProtectionProfileID.ENHANCED]
        self.assertFalse(enhanced.selectable)
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.ENHANCED].selectable)
        self.assertIs(enhanced.failure_disposition, FailureDisposition.DENY)
        self.assertEqual(
            {item.control for item in enhanced.requirements
             if item.availability is ControlAvailability.CURRENT},
            set(BASELINE_CONTROLS),
        )
        self.assertIn(
            (PolicyControl.PDF_STRUCTURE_VALIDATION, ControlAvailability.PLANNED),
            {(item.control, item.availability) for item in enhanced.requirements},
        )

        for name, user_password, owner_password in CASES:
            with self.subTest(case=name):
                contents = password_protected_pdf(user_password, owner_password)
                self.assertIs(
                    inspect_pdf_encryption(contents).status,
                    PDFEncryptionStatus.ENCRYPTED,
                )
                preferences = {
                    SELECTED_PROFILE_KEY: "enhanced",
                    "customBrowser": "com.example.preferred-browser",
                    "customSetting": {"keep": True},
                }
                original_preferences = {
                    **preferences, "customSetting": preferences["customSetting"].copy(),
                }
                with (
                    patch("subprocess.run",
                          side_effect=AssertionError("unexpected scan")) as scan,
                    patch("subprocess.Popen",
                          side_effect=AssertionError("unexpected handoff")) as handoff,
                ):
                    with self.assertRaises(UnsupportedEffectivePolicy):
                        resolve_effective_policy(preferences)
                scan.assert_not_called()
                handoff.assert_not_called()
                self.assertEqual(preferences, original_preferences)
                self.assertTrue(PdfReader(BytesIO(contents), strict=True).is_encrypted)

    def test_builtin_scan_floor_remains_independent_of_planned_enhanced(self):
        active = resolve_effective_policy()
        self.assertEqual(active.profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(active.required_checks, frozenset(BASELINE_CONTROLS))
        self.assertIs(active.failure_disposition, FailureDisposition.DENY)
        self.assertFalse(active.optional_checks)

        # The deployed scanner, not this passive evidence, remains the gate.
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("--alert-encrypted=yes", gate)
        self.assertNotIn("pdf_encryption_policy", gate)

    def test_both_ci_workflows_execute_password_protected_regression(self):
        command = "PYTHONPATH=. python3 tests/enhanced/password-protected.py -v"
        for workflow in ("ci.yml", "consolidated-checks.yml"):
            with self.subTest(workflow=workflow):
                contents = (ROOT / ".github/workflows" / workflow).read_text(
                    encoding="utf-8"
                )
                self.assertIn(command, contents)


if __name__ == "__main__":
    unittest.main()
