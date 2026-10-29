#!/usr/bin/env python3
"""opener-0513: generated PDFs must never be presented as original content."""
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from unittest.mock import patch
import unittest

from maximum_sanitized_copy import (
    CONVERSION_CHANGE_WARNING, GENERATED_CONTENT_ORIGIN, OFFER_EXPLANATION,
    OFFER_LABEL, SanitizedCopyOffer,
)
from maximum_safe_copy_handoff import MaximumSafeCopyHandoff
from maximum_generated_rescan import verified_generated_pdf_bytes

class GeneratedCopyOriginTests(unittest.TestCase):
    def test_offer_fixed_label_and_origin_are_explicit(self):
        offer = SanitizedCopyOffer(b"%PDF-1.4\nsynthetic output", 1)
        self.assertEqual(offer.content_origin, "generatedContent")
        self.assertEqual(offer.label, "Save generated sanitized PDF copy")
        self.assertIn("not the untouched original", offer.explanation)
        self.assertEqual(offer.to_public_metadata(), {
            "contentOrigin": "generatedContent",
            "isUntouchedOriginal": False,
            "label": OFFER_LABEL,
            "explanation": OFFER_EXPLANATION,
            "conversionWarning": CONVERSION_CHANGE_WARNING,
            "requiresFreshScan": True,
            "authorizesOpen": False,
            "ocrRestored": False,
        })
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        with self.assertRaises(FrozenInstanceError):
            offer.content_origin = "original"

    def test_flattening_warning_explains_selectable_text_loss(self):
        offer = SanitizedCopyOffer(b"%PDF-1.4\\nsynthetic output", 1)
        for message in (offer.explanation, offer.to_public_metadata()["explanation"]):
            with self.subTest(message=message):
                self.assertIn(
                    "Flattening pages into images can remove selectable text", message
                )
                self.assertIn("searchability", message)
                self.assertIn("scan the generated copy separately", message)
                self.assertNotIn("synthetic output", message)

    def test_cannot_relabel_generated_offer_as_original(self):
        params = {"pdf_bytes": b"%PDF-synthetic", "page_count": 1}
        for change in (
            {"content_origin": "original"},
            {"content_origin": ""},
            {"content_origin": None},
            {"content_origin": True},
            {"label": "Save untouched original"},
            {"explanation": "Unmodified source"},
            {"needs_separate_scan": False},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                SanitizedCopyOffer(**params, **change)
        with self.assertRaises(ValueError):
            replace(SanitizedCopyOffer(**params), content_origin="original")

    def test_handoff_preserves_generated_identity_without_paths(self):
        handoff = MaximumSafeCopyHandoff(Path("/tmp/synthetic-safe-copy.pdf"))
        self.assertEqual(handoff.content_origin, GENERATED_CONTENT_ORIGIN)
        self.assertEqual(handoff.display_label, OFFER_LABEL)
        self.assertEqual(handoff.to_public_metadata(), {
            "contentOrigin": "generatedContent",
            "isUntouchedOriginal": False,
            "label": OFFER_LABEL,
            "conversionWarning": CONVERSION_CHANGE_WARNING,
            "freshlyScanned": True,
            "originalOpened": False,
        })
        self.assertNotIn("/tmp/", str(handoff.to_public_metadata()))
        with self.assertRaises(FrozenInstanceError):
            handoff.content_origin = "original"
        for modification in (
            {"content_origin": "original"},
            {"content_origin": ""},
            {"display_label": "Untouched original"},
            {"original_opened": True},
            {"scanned": False},
        ):
            with self.subTest(modification=modification), self.assertRaises(ValueError):
                MaximumSafeCopyHandoff(Path("/tmp/synthetic-safe-copy.pdf"), **modification)

    def test_rescan_fails_before_any_pdf_validation_if_marker_tampered(self):
        offer = SanitizedCopyOffer(b"%PDF-synthetic", 1)
        with patch("maximum_sanitized_copy._passive_pages", return_value=True) as verify:
            self.assertEqual(verified_generated_pdf_bytes(offer), offer.pdf_bytes)
            self.assertEqual(verify.call_count, 1)
            object.__setattr__(offer, "content_origin", "original")
            self.assertIsNone(verified_generated_pdf_bytes(offer))
            self.assertEqual(verify.call_count, 1)

    def test_provenance_does_not_change_installed_scan_or_pdf_metadata(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text(encoding="utf-8")
        source = (root / "maximum_sanitized_copy.py").read_text(encoding="utf-8")
        rescan = (root / "maximum_generated_rescan.py").read_text(encoding="utf-8")
        route = (root / "maximum_safe_copy_handoff.py").read_text(encoding="utf-8")
        workflow = (root / ".github/workflows/maximum-generated-content-marking.yml").read_text(encoding="utf-8")
        self.assertNotIn("maximum_generated_content_marking", scanner)
        self.assertIn("force_rescan=True", scanner)
        self.assertIn("GENERATED_CONTENT_ORIGIN", source)
        self.assertIn("GENERATED_CONTENT_ORIGIN", route)
        self.assertIn("GENERATED_CONTENT_ORIGIN", rescan)
        self.assertIn("test-maximum-generated-content-marking.py -v", workflow)
        self.assertNotIn("writer.add_metadata(", source)

if __name__ == "__main__":
    unittest.main()
