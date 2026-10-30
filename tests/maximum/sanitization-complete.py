#!/usr/bin/env python3
"""opener-0549: completion appears only after verified Maximum raster conversion."""

from io import BytesIO
import sys
import unittest

from pypdf import PdfWriter

import maximum_sanitized_copy as sanitizer


class SanitizationCompletionPresentationTests(unittest.TestCase):
    def test_verified_offer_and_decision_report_completion_not_scan_approval(self):
        offer = sanitizer.SanitizedCopyOffer(b"%PDF-1.4\nsynthetic PDF output", 1)
        decision = sanitizer.SanitizationDecision(offer, None)
        for payload in (offer.to_public_metadata(), decision.to_dict()):
            with self.subTest(payload=payload):
                self.assertIs(payload["sanitizationComplete"], True)
                self.assertEqual(payload["sanitizationStatus"], "complete")
                self.assertEqual(
                    payload["sanitizationStatusLabel"],
                    sanitizer.SANITIZATION_COMPLETE_LABEL,
                )
                self.assertIn("separate scan before opening", payload["sanitizationStatusLabel"])
                self.assertNotIn("synthetic PDF output", str(payload))
        self.assertIs(offer.to_public_metadata()["authorizesOpen"], False)
        self.assertIs(decision.to_dict()["permitsOpen"], False)
        self.assertIs(decision.to_dict()["requiresSeparateScan"], True)
        self.assertEqual(decision.action, "offerForSeparateScan")

    def test_every_blocked_decision_withholds_completion(self):
        for reason in sanitizer.SanitizationBlockReason:
            with self.subTest(reason=reason):
                result = sanitizer.SanitizationDecision(None, reason).to_dict()
                self.assertIs(result["sanitizationComplete"], False)
                self.assertEqual(result["sanitizationStatus"], "notCompleted")
                self.assertEqual(
                    result["sanitizationStatusLabel"],
                    sanitizer.SANITIZATION_NOT_COMPLETE_LABEL,
                )
                self.assertIs(result["offerAvailable"], False)
                self.assertIs(result["permitsOpen"], False)
                self.assertNotIn("conversionWarning", result)

    def test_every_sanitizer_failure_withholds_completion_and_scan_verdict(self):
        for kind in sanitizer.SanitizerFailureKind:
            with self.subTest(kind=kind):
                failure = sanitizer._failed(kind)
                self.assertIsNone(failure.offer)
                result = failure.failure.to_dict()
                self.assertIs(result["sanitizationComplete"], False)
                self.assertEqual(result["sanitizationStatus"], "notCompleted")
                self.assertEqual(
                    result["sanitizationStatusLabel"],
                    sanitizer.SANITIZATION_NOT_COMPLETE_LABEL,
                )
                self.assertEqual(result["scanVerdict"], "notAssessed")
                self.assertIs(result["permitsOpen"], False)

    def test_unsupported_input_never_reports_complete(self):
        result = sanitizer.assess_sanitized_pdf_copy(b"not a PDF").to_dict()
        self.assertEqual(result["action"], "block")
        self.assertIs(result["sanitizationComplete"], False)
        self.assertEqual(result["sanitizationStatus"], "notCompleted")

    @unittest.skipUnless(sys.platform == "darwin", "Native raster conversion requires macOS")
    def test_real_native_conversion_indicates_completion_after_verification(self):
        writer = PdfWriter()
        writer.add_blank_page(width=180, height=220)
        source = BytesIO()
        writer.write(source)
        decision = sanitizer.assess_sanitized_pdf_copy(source.getvalue())
        self.assertEqual(decision.action, "offerForSeparateScan")
        self.assertIs(decision.to_dict()["sanitizationComplete"], True)
        self.assertEqual(decision.to_dict()["sanitizationStatus"], "complete")
        self.assertIs(decision.permits_open, False)


if __name__ == "__main__":
    unittest.main()
