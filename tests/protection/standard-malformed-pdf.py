#!/usr/bin/env python3
"""opener-1011: test malformed PDF handling at the planned Standard boundary.

Standard is not an executable protection profile. This regression verifies
that a real malformed PDF cannot be used to admit Standard, while the optional
PDF parser returns non-authorizing failure evidence. It deliberately does not
simulate an active Standard scan or change the installed Built-in scan gate.
"""

from hashlib import sha256
from pathlib import Path
import unittest

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from pdf_structure_parser import (
    PDFStructureFailureCode,
    PDFStructureParseFailure,
    parse_pdf_structure_result,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    ControlAvailability,
    FailureDisposition,
    PolicyControl,
    protection_policy_definition,
)
from protection_profiles import ProtectionProfileID, protection_profile_definition
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


def malformed_reference_pdf():
    """Preserve a valid PDF header and objects but remove its required trailer."""
    valid = REFERENCE_PDFS[0].content
    assert valid.startswith(b"%PDF-1.4\n") and valid.endswith(b"%%EOF\n")
    assert valid.count(b"trailer\n") == 1
    return valid.split(b"trailer\n", 1)[0]


class StandardMalformedPDFTests(unittest.TestCase):
    def test_reference_pdf_has_an_actual_structural_failure(self):
        malformed = malformed_reference_pdf()
        self.assertTrue(malformed.startswith(b"%PDF-1.4\n"))
        self.assertIn(b"xref\n", malformed)
        self.assertNotIn(b"trailer\n", malformed)
        self.assertNotIn(b"%%EOF", malformed)
        self.assertNotEqual(sha256(malformed).digest(),
                            sha256(REFERENCE_PDFS[0].content).digest())

        evidence = parse_pdf_structure_result(malformed)
        self.assertIs(type(evidence), PDFStructureParseFailure)
        self.assertIs(evidence.code, PDFStructureFailureCode.invalidStructure)
        self.assertEqual(evidence.to_dict()["status"], "failure")
        self.assertIs(evidence.to_dict()["authorizesOpen"], False)

    def test_standard_cannot_be_activated_for_malformed_pdf(self):
        malformed = malformed_reference_pdf()
        self.assertIsInstance(malformed, bytes)
        definition = protection_profile_definition(ProtectionProfileID.STANDARD)
        policy = protection_policy_definition(ProtectionProfileID.STANDARD)
        self.assertEqual(definition.display_name, "Standard")
        self.assertFalse(definition.selectable)
        self.assertFalse(policy.selectable)
        self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
        self.assertEqual({check.control for check in policy.required_checks},
                         set(BASELINE_CONTROLS))
        self.assertEqual(tuple(
            (check.control, check.availability) for check in policy.optional_checks
        ), ((PolicyControl.PDF_STRUCTURE_VALIDATION, ControlAvailability.PLANNED),))

        preferences = {
            SELECTED_PROFILE_KEY: ProtectionProfileID.STANDARD.value,
            "customPDFBrowser": "preserve-user-choice",
            "showScanProgress": False,
        }
        original = dict(preferences)
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy(preferences)
        self.assertEqual(preferences, original)
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(ACTIVE_PROFILE_ID, "built-in")

    def test_unsupported_standard_is_not_silently_wired_to_active_scanner(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertNotIn("protection_profiles", scanner)
        self.assertNotIn("effective_protection_policy", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/protection/standard-malformed-pdf.py -v",
                      workflow)


if __name__ == "__main__":
    unittest.main()
