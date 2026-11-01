#!/usr/bin/env python3
"""opener-1020: reject malformed PDFs at Maximum's inactive policy boundary.

Maximum is not yet an executable profile. Validate a genuinely damaged PDF
against its planned structural and sanitizer stages without manufacturing a
clean verdict, invoking the installed scanner, or changing user settings.
"""

from hashlib import sha256
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
from maximum_sanitized_copy import (
    SanitizationBlockReason,
    assess_sanitized_pdf_copy,
)
import maximum_sanitized_copy as sanitizer
from pdf_malformed_structures import (
    BLOCK_MESSAGE,
    PDFMalformedStructureError,
    inspect_pdf_malformed_structures,
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
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("maximum_malformed_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
CLEAN_PDF = next(sample for sample in REFERENCE_PDFS
                 if sample.identifier == "clean-basic")


def malformed_reference_pdf():
    """Keep real PDF objects and xref but truncate the required trailer/EOF."""
    valid = CLEAN_PDF.content
    assert valid.startswith(b"%PDF-1.4\n") and valid.endswith(b"%%EOF\n")
    assert valid.count(b"trailer\n") == 1
    return valid.split(b"trailer\n", 1)[0]


class MaximumMalformedPDFTests(unittest.TestCase):
    def test_real_malformed_reference_fails_inherited_structure_checks(self):
        malformed = malformed_reference_pdf()
        self.assertIn(b"xref\n", malformed)
        self.assertNotIn(b"trailer\n", malformed)
        self.assertNotIn(b"%%EOF", malformed)
        self.assertNotEqual(sha256(malformed).digest(), sha256(CLEAN_PDF.content).digest())

        evidence = parse_pdf_structure_result(malformed)
        self.assertIs(type(evidence), PDFStructureParseFailure)
        self.assertIs(evidence.code, PDFStructureFailureCode.invalidStructure)
        self.assertEqual(evidence.to_dict()["failureCode"], "invalidStructure")
        self.assertIs(evidence.to_dict()["authorizesOpen"], False)
        with self.assertRaises(PDFMalformedStructureError) as raised:
            inspect_pdf_malformed_structures(malformed)
        self.assertEqual(str(raised.exception), BLOCK_MESSAGE)

    def test_maximum_sanitization_blocks_malformed_source_before_conversion(self):
        malformed = malformed_reference_pdf()
        original = bytes(malformed)
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/usr/bin/true")), \
             patch.object(sanitizer, "run_limited_converter") as convert:
            decision = assess_sanitized_pdf_copy(malformed)
            convert.assert_not_called()

        self.assertIs(decision.blocked_reason, SanitizationBlockReason.unreadableSource)
        self.assertEqual(decision.action, "block")
        self.assertIsNone(decision.offer)
        self.assertFalse(decision.permits_open)
        self.assertFalse(decision.allow_fallback)
        self.assertFalse(decision.allow_clean_cache)
        self.assertTrue(decision.preserve_quarantine)
        self.assertTrue(decision.requires_separate_scan)
        self.assertIs(decision.to_dict()["sanitizationComplete"], False)
        self.assertEqual(malformed, original)
        self.assertEqual(CLEAN_PDF.content[-6:], b"%%EOF\n")

    def test_planned_maximum_does_not_authorize_scanner_or_mutate_settings(self):
        profile = protection_profile_definition(ProtectionProfileID.MAXIMUM)
        policy = protection_policy_definition(ProtectionProfileID.MAXIMUM)
        self.assertEqual(profile.display_name, "Maximum")
        self.assertFalse(profile.selectable)
        self.assertFalse(policy.selectable)
        self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
        checks = {item.control: item.availability for item in policy.required_checks}
        self.assertTrue(set(BASELINE_CONTROLS) <= set(checks))
        self.assertEqual(
            {control for control, availability in checks.items()
             if availability is ControlAvailability.PLANNED},
            {PolicyControl.PDF_STRUCTURE_VALIDATION,
             PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS},
        )
        self.assertFalse(policy.optional_checks)

        preferences = {
            SELECTED_PROFILE_KEY: ProtectionProfileID.MAXIMUM.value,
            "customPDFBrowser": "preserve-custom-viewer",
            "showScanProgress": False,
        }
        before = dict(preferences)
        with patch.object(gate, "scan_and_open") as scan:
            with self.assertRaises(UnsupportedEffectivePolicy):
                resolve_effective_policy(preferences)
            scan.assert_not_called()
        self.assertEqual(preferences, before)
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)
        self.assertEqual(ACTIVE_PROFILE_ID, "built-in")

    def test_ci_covers_maximum_malformed_pdf_without_altering_live_gate(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("maximum_sanitized_copy", scanner)
        self.assertNotIn("effective_protection_policy", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/protection/maximum-malformed-pdf.py -v",
                      workflow)


if __name__ == "__main__":
    unittest.main()
