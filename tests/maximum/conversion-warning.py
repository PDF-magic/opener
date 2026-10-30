#!/usr/bin/env python3
"""opener-0532: material PDF-to-raster changes must trigger a fixed warning."""

from dataclasses import FrozenInstanceError, replace
from io import BytesIO
from pathlib import Path
import sys
import unittest

from pypdf import PdfWriter

import maximum_sanitized_copy as copies
from maximum_safe_copy_handoff import MaximumSafeCopyHandoff


class ConversionChangeWarningTests(unittest.TestCase):
    def setUp(self):
        self.offer = copies.SanitizedCopyOffer(b"%PDF-1.4\nsynthetic output", 1)

    def test_fixed_warning_describes_meaningful_changes(self):
        message = copies.CONVERSION_CHANGE_WARNING
        self.assertTrue(message.startswith("Warning:"))
        for phrase in ("meaningfully changes", "flattened page images",
                       "Searchable text", "forms", "links", "annotations",
                       "metadata", "visual details", "Review"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, message)
        self.assertEqual(self.offer.warning, message)
        self.assertEqual(
            copies.SanitizedCopyOffer(b"%PDF-1.4\nprivate source string", 2).warning,
            message,
        )
        self.assertNotIn("private source string", message)

    def test_successful_offer_and_decision_publish_warning(self):
        metadata = self.offer.to_public_metadata()
        self.assertEqual(metadata["conversionWarning"], self.offer.warning)
        self.assertFalse(metadata["isUntouchedOriginal"])
        self.assertTrue(metadata["requiresFreshScan"])
        self.assertFalse(metadata["authorizesOpen"])
        decision = copies.SanitizationDecision(self.offer, None)
        self.assertEqual(decision.action, "offerForSeparateScan")
        self.assertEqual(decision.to_dict()["conversionWarning"], self.offer.warning)
        self.assertFalse(decision.permits_open)
        self.assertTrue(decision.requires_separate_scan)

    def test_blocked_decision_does_not_offer_a_copy(self):
        blocked = copies.SanitizationDecision(
            None, copies.SanitizationBlockReason.conversionFailed,
        )
        self.assertEqual(blocked.action, "block")
        self.assertFalse(blocked.to_dict()["offerAvailable"])
        self.assertNotIn("conversionWarning", blocked.to_dict())

    def test_warning_survives_post_scan_handoff_metadata(self):
        handoff = MaximumSafeCopyHandoff(Path("/tmp/synthetic-copy.pdf"))
        public = handoff.to_public_metadata()
        self.assertEqual(public["conversionWarning"], self.offer.warning)
        self.assertTrue(public["freshlyScanned"])
        self.assertFalse(public["isUntouchedOriginal"])
        self.assertFalse(public["originalOpened"])
        self.assertNotIn("/tmp/", str(public))

    def test_offer_cannot_hide_or_relabel_warning(self):
        for value in ("", None, False, "No changes were made"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                replace(self.offer, warning=value)
        with self.assertRaises(FrozenInstanceError):
            self.offer.warning = "No warning"
        self.assertEqual(self.offer.to_public_metadata()["conversionWarning"],
                         copies.CONVERSION_CHANGE_WARNING)

    @unittest.skipUnless(sys.platform == "darwin", "Native raster conversion needs macOS")
    def test_real_converted_pdf_offer_exposes_warning(self):
        writer = PdfWriter()
        writer.add_blank_page(width=180, height=220)
        data = BytesIO()
        writer.write(data)
        offer = copies.offer_sanitized_pdf_copy(data.getvalue())
        self.assertIsNotNone(offer)
        self.assertEqual(offer.warning, copies.CONVERSION_CHANGE_WARNING)
        self.assertEqual(
            offer.to_public_metadata()["conversionWarning"],
            copies.CONVERSION_CHANGE_WARNING,
        )
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)


if __name__ == "__main__":
    unittest.main()
