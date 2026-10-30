#!/usr/bin/env python3
"""opener-0530: OCR restoration is not part of the sanitized-copy security gate.

The current Maximum converter intentionally discards searchable text. A future
optional OCR feature must not be enabled by changing this offer's metadata.
"""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import sys
import unittest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import maximum_sanitized_copy as copies
from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID

ROOT = Path(__file__).resolve().parents[2]


def _vector_text_pdf():
    """Create non-sensitive, searchable source text without external fixtures."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=240, height=180)
    font = writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    }))
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 14 Tf 20 95 Td (Visible source text 123) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class OCRSeparationContractTests(unittest.TestCase):
    def test_offer_explicitly_disclaims_restored_searchable_text(self):
        offer = copies.SanitizedCopyOffer(_vector_text_pdf(), 1)
        self.assertFalse(offer.ocr_restored)
        self.assertIn("OCR restoration is not included", offer.explanation)
        self.assertEqual(offer.to_public_metadata()["ocrRestored"], False)
        self.assertTrue(offer.to_public_metadata()["requiresFreshScan"])
        self.assertFalse(offer.to_public_metadata()["authorizesOpen"])
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)

    def test_caller_cannot_mark_unmodified_offer_as_ocr_restored(self):
        source = _vector_text_pdf()
        with self.assertRaises(ValueError):
            copies.SanitizedCopyOffer(source, 1, ocr_restored=True)
        with self.assertRaises(ValueError):
            copies.SanitizedCopyOffer(source, 1, ocr_restored=1)
        offer = copies.SanitizedCopyOffer(source, 1)
        with self.assertRaises(FrozenInstanceError):
            offer.ocr_restored = True

    def test_original_text_is_searchable_but_ocr_is_not_implicit(self):
        source = PdfReader(BytesIO(_vector_text_pdf()), strict=True)
        self.assertEqual(len(source.pages), 1)
        self.assertIn("Visible source text 123", source.pages[0].extract_text())

    def test_ocr_does_not_change_active_scanner_or_enable_maximum(self):
        scan_gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scan_gate)
        self.assertNotIn("maximum_ocr_restoration", scan_gate)
        self.assertNotIn("maximum_sanitized_copy", scan_gate)
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


@unittest.skipUnless(sys.platform == "darwin", "Native CoreGraphics converter requires macOS")
class NativeOCRSeparationTests(unittest.TestCase):
    def test_actual_rasterized_offer_contains_no_searchable_ocr_text(self):
        source = _vector_text_pdf()
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offer, "Native converter must return a verified PDF offer")
        self.assertNotEqual(offer.pdf_bytes, source)
        self.assertFalse(offer.ocr_restored)
        self.assertFalse(offer.to_public_metadata()["ocrRestored"])
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        pages = PdfReader(BytesIO(offer.pdf_bytes), strict=True).pages
        self.assertEqual(len(pages), 1)
        self.assertEqual((pages[0].extract_text() or "").strip(), "")
        self.assertEqual(len(pages[0].images), 1)


if __name__ == "__main__":
    unittest.main()
