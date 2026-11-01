#!/usr/bin/env python3
"""opener-1021: unsupported features block planned Maximum protection.

The PDF is structurally valid but contains a portfolio collection, which the
static Maximum rasterizer cannot faithfully convert. Maximum is not an active
scanner profile; this checks passive feature/sanitization decisions only.
"""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject

from effective_protection_policy import (
    ACTIVE_PROFILE_ID,
    SELECTED_PROFILE_KEY,
    UnsupportedEffectivePolicy,
    resolve_effective_policy,
)
import maximum_sanitized_copy as sanitizer
from pdf_unsupported_feature_inspection import (
    UnsupportedPDFFeature,
    inspect_pdf_unsupported_features,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS,
    ControlAvailability,
    FailureDisposition,
    PolicyControl,
    protection_policy_definition,
)
from protection_profiles import ProtectionProfileID, protection_profile_definition


ROOT = Path(__file__).resolve().parents[2]


def unsupported_portfolio_pdf():
    """Construct a parseable one-page PDF with unsupported portfolio metadata."""
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=250)
    writer._root_object[NameObject("/Collection")] = writer._add_object(DictionaryObject())
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class MaximumUnsupportedFeatureTests(unittest.TestCase):
    def test_real_pdf_is_valid_but_has_an_explicitly_unsupported_feature(self):
        data = unsupported_portfolio_pdf()
        reader = PdfReader(BytesIO(data), strict=True)
        self.assertEqual(len(reader.pages), 1)
        self.assertIn("/Collection", reader.trailer["/Root"])

        report = inspect_pdf_unsupported_features(data)
        self.assertIn(UnsupportedPDFFeature.PDF_PORTFOLIO, report.feature_codes)
        self.assertTrue(report.has_unsupported_features)
        self.assertFalse(report.inspection_complete)
        self.assertFalse(report.authorizes_open)
        self.assertIs(report.to_dict()["authorizesOpen"], False)

    def test_maximum_selection_is_rejected_without_changing_preferences(self):
        definition = protection_profile_definition(ProtectionProfileID.MAXIMUM)
        policy = protection_policy_definition(ProtectionProfileID.MAXIMUM)
        self.assertEqual(definition.display_name, "Maximum")
        self.assertFalse(definition.selectable)
        self.assertFalse(policy.selectable)
        self.assertIs(policy.failure_disposition, FailureDisposition.DENY)
        availability = {check.control: check.availability
                        for check in policy.required_checks}
        self.assertTrue(set(BASELINE_CONTROLS).issubset(availability))
        self.assertIs(availability[PolicyControl.PDF_STRUCTURE_VALIDATION],
                      ControlAvailability.PLANNED)
        self.assertIs(availability[PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS],
                      ControlAvailability.PLANNED)

        preferences = {
            SELECTED_PROFILE_KEY: ProtectionProfileID.MAXIMUM.value,
            "customPDFBrowser": "com.example.UserSelection",
            "showScanProgress": False,
        }
        original = dict(preferences)
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy(preferences)
        self.assertEqual(preferences, original)
        self.assertEqual(resolve_effective_policy().profile_id, ACTIVE_PROFILE_ID)

    def test_unsupported_feature_blocks_conversion_and_all_open_shortcuts(self):
        data = unsupported_portfolio_pdf()
        digest = sha256(data).digest()
        with patch.object(sanitizer, "_trusted_converter",
                          return_value=Path("/mock/renderer")), \
             patch.object(sanitizer, "run_limited_converter") as convert, \
             patch.object(sanitizer, "remove_active_pdf_functionality") as rebuild:
            decision = sanitizer.assess_sanitized_pdf_copy(data)
            self.assertIsNone(sanitizer.offer_sanitized_pdf_copy(data))
            convert.assert_not_called()
            rebuild.assert_not_called()

        self.assertEqual(decision.action, "block")
        self.assertIs(decision.blocked_reason,
                      sanitizer.SanitizationBlockReason.unsupportedFeature)
        self.assertIsNone(decision.offer)
        self.assertFalse(decision.permits_open)
        self.assertFalse(decision.allow_fallback)
        self.assertFalse(decision.allow_clean_cache)
        self.assertTrue(decision.preserve_quarantine)
        self.assertTrue(decision.requires_separate_scan)
        public = decision.to_dict()
        self.assertEqual(public["reason"], "unsupportedFeature")
        self.assertIs(public["sanitizationComplete"], False)
        self.assertIs(public["offerAvailable"], False)
        self.assertIs(public["permitsOpen"], False)
        self.assertEqual(sha256(data).digest(), digest)
        self.assertNotIn("/Collection", str(public))

    def test_required_ci_executes_unsupported_maximum_regression(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONPATH=. python3 tests/protection/maximum-unsupported-feature.py -v",
            workflow,
        )
        installed = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("maximum_sanitized_copy", installed)


if __name__ == "__main__":
    unittest.main()
