#!/usr/bin/env python3
"""opener-1023: Maximum must fail closed when generated output fails validation.

Maximum remains planned and unselectable. Exercise the existing sanitizer's
independent output gates with synthetic, non-executable converter results;
never bypass the installed Built-in ClamAV scan and handoff policy.
"""

from io import BytesIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

import maximum_sanitized_copy as sanitizer
from maximum_sanitized_structure import SanitizedPDFStructure
from protection_profiles import ProtectionProfileID, protection_profile_definition
from effective_protection_policy import (
    SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy, resolve_effective_policy,
)


ROOT = Path(__file__).resolve().parents[2]


def sample_pdf(*, with_javascript=False):
    writer = PdfWriter()
    writer.add_blank_page(width=180, height=240)
    if with_javascript:
        writer.add_js("app.alert('PRIVATE-GENERATED-CONTENT')")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class MaximumInvalidOutputTests(unittest.TestCase):
    def setUp(self):
        self.source = sample_pdf()
        # The converter is always mocked: no system renderer is invoked.
        self.converted = self.source + b"\nsynthetic-conversion-result"

    def converter(self, output=None):
        return (
            patch.object(sanitizer, "_trusted_converter",
                         return_value=Path("/usr/bin/true")),
            patch.object(sanitizer, "run_limited_converter",
                         return_value=subprocess.CompletedProcess(
                             [], 0, self.converted if output is None else output
                         )),
        )

    def assert_rejected(self):
        original = self.source
        attempt = sanitizer.attempt_sanitized_pdf_copy(original)
        self.assertIsNone(attempt.offer)
        self.assertIsNotNone(attempt.failure)
        self.assertIs(attempt.failure.kind, sanitizer.SanitizerFailureKind.INVALID_OUTPUT)
        self.assertIs(attempt.permits_open, False)
        failure = attempt.failure.to_dict()
        self.assertEqual(failure["status"], "sanitizerFailure")
        self.assertEqual(failure["kind"], "sanitizerInvalidOutput")
        self.assertEqual(failure["scanVerdict"], "notAssessed")
        self.assertIs(failure["permitsOpen"], False)
        self.assertIs(failure["sanitizationComplete"], False)
        self.assertEqual(failure["sanitizationStatus"], "notCompleted")
        self.assertNotIn("PRIVATE-", str(failure))
        self.assertNotIn(str(ROOT), str(failure))

        decision = sanitizer.assess_sanitized_pdf_copy(original)
        self.assertIsNone(decision.offer)
        self.assertIs(decision.blocked_reason,
                      sanitizer.SanitizationBlockReason.outputUnverified)
        self.assertEqual(decision.action, "block")
        self.assertIs(decision.permits_open, False)
        self.assertIs(decision.allow_fallback, False)
        self.assertIs(decision.allow_clean_cache, False)
        self.assertIs(decision.preserve_quarantine, True)
        self.assertIs(decision.requires_separate_scan, True)
        metadata = decision.to_dict()
        self.assertIs(metadata["offerAvailable"], False)
        self.assertIs(metadata["sanitizationComplete"], False)
        self.assertIs(metadata["permitsOpen"], False)
        self.assertIs(metadata["allowCleanCache"], False)
        self.assertEqual(metadata["sanitizationStatus"], "notCompleted")
        self.assertNotIn("conversionWarning", metadata)

        self.assertIsNone(sanitizer.offer_sanitized_pdf_copy(original))
        self.assertEqual(self.source, original)

    def test_converter_without_valid_bytes_never_reaches_rebuilder(self):
        for output in (b"", self.source, bytearray(b"%PDF-1.4\ninvalid")):
            with self.subTest(output_type=type(output).__name__,
                              length=len(output)):
                trusted, run = self.converter(output)
                with trusted, run, patch.object(
                    sanitizer, "remove_active_pdf_functionality"
                ) as rebuild:
                    self.assert_rejected()
                    rebuild.assert_not_called()

    def test_rebuilt_pdf_with_active_javascript_is_not_offered(self):
        generated = sample_pdf(with_javascript=True)
        self.assertNotEqual(generated, self.source)
        self.assertFalse(sanitizer._passive_pages(generated, 1))
        trusted, run = self.converter()
        with trusted, run, patch.object(
            sanitizer, "remove_active_pdf_functionality",
            return_value=generated,
        ), patch.object(sanitizer, "verify_sanitized_pdf_structure") as verify:
            self.assert_rejected()
            verify.assert_not_called()

    def test_trailing_data_rejected_by_independent_structure_validator(self):
        generated = sample_pdf() + b"\nPRIVATE-TRAILING-DATA"
        trusted, run = self.converter()
        with trusted, run, patch.object(
            sanitizer, "remove_active_pdf_functionality",
            return_value=generated,
        ), patch.object(
            sanitizer, "_passive_pages", return_value=True,
        ), patch.object(
            sanitizer, "verify_sanitized_pdf_structure",
            wraps=sanitizer.verify_sanitized_pdf_structure,
        ) as verify:
            # Isolate the independent final-structure gate after passive checks.
            self.assert_rejected()
            self.assertEqual(verify.call_count, 3)
            verify.assert_called_with(generated, 1)

    def test_mismatched_verified_page_count_cannot_be_offered(self):
        # Distinct from the original so the independent count gate is reached.
        generated = sample_pdf() + b"\nsynthetic-rebuilt-copy"
        trusted, run = self.converter()
        with trusted, run, patch.object(
            sanitizer, "remove_active_pdf_functionality",
            return_value=generated,
        ), patch.object(
            sanitizer, "_passive_pages", return_value=True,
        ), patch.object(
            sanitizer, "verify_sanitized_pdf_structure",
            return_value=SanitizedPDFStructure(2, 5),
        ) as verify:
            self.assert_rejected()
            self.assertEqual(verify.call_count, 3)

    def test_invalid_output_cannot_activate_maximum_or_change_scan_gate(self):
        definition = protection_profile_definition(ProtectionProfileID.MAXIMUM)
        self.assertFalse(definition.selectable)
        preferences = {
            SELECTED_PROFILE_KEY: ProtectionProfileID.MAXIMUM.value,
            "customPDFBrowser": "keep-selected-browser",
            "showScanProgress": False,
        }
        original = dict(preferences)
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy(preferences)
        self.assertEqual(preferences, original)
        self.assertEqual(resolve_effective_policy().profile_id, "built-in")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("attempt_sanitized_pdf_copy", scanner)
        self.assertNotIn("assess_sanitized_pdf_copy", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)


if __name__ == "__main__":
    unittest.main()
