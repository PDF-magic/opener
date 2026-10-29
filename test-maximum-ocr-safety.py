#!/usr/bin/env python3
"""opener-0531: simulated OCR cannot restore active PDF content."""

from io import BytesIO
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
import zlib

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject,
    NumberObject, StreamObject, TextStringObject,
)

import maximum_sanitized_copy as copies
from maximum_active_content_removal import remove_active_pdf_functionality
from maximum_generated_rescan import verified_generated_pdf_bytes


def raster_fixture():
    """A synthetic image-only PDF; no real documents or private files."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=72, height=90)
    image = StreamObject()
    image._data = zlib.compress(Image.new("RGB", (16, 20), (5, 85, 190)).tobytes())
    image.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(16),
        NameObject("/Height"): NumberObject(20),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/Filter"): NameObject("/FlateDecode"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/XObject"): DictionaryObject({
            NameObject("/Im0"): writer._add_object(image),
        }),
    })
    content = DecodedStreamObject()
    content.set_data(b"q 72 0 0 90 0 0 cm /Im0 Do Q\n")
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def post_ocr_copy(original, *, overlay=b"", active_feature=None):
    """Simulate an OCR engine mutating final PDF bytes after verification."""
    writer = PdfWriter()
    writer.append(BytesIO(original))
    # pypdf appends an incidental /Outlines entry; remove it so the
    # negative test reaches the OCR-content gate, not a catalog check.
    writer._root_object.pop(NameObject("/Outlines"), None)
    page = writer.pages[0]
    if overlay:
        commands = page["/Contents"].get_object().get_data()
        stream = DecodedStreamObject()
        stream.set_data(commands + overlay)
        page[NameObject("/Contents")] = writer._add_object(stream)
    if active_feature == "javascript":
        writer.add_js("app.alert('OCR-injected script');")
    elif active_feature == "openAction":
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject({
            NameObject("/S"): NameObject("/JavaScript"),
            NameObject("/JS"): TextStringObject("app.alert('OCR');"),
        })
    elif active_feature == "annotation":
        page[NameObject("/Annots")] = ArrayObject([
            writer._add_object(DictionaryObject({
                NameObject("/Subtype"): NameObject("/Text"),
                NameObject("/A"): DictionaryObject({
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/URI"): TextStringObject("https://example.invalid/"),
                }),
            })),
        ])
    elif active_feature == "attachment":
        writer.add_attachment("ocr-added.txt", b"never-copy-ocr-attachment")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class OCRBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.raster = raster_fixture()
        self.clean = remove_active_pdf_functionality(self.raster, 1)
        self.assertIsNotNone(self.clean)
        self.assertTrue(copies._passive_pages(self.clean, 1))
        self.assertEqual(
            verified_generated_pdf_bytes(copies.SanitizedCopyOffer(self.clean, 1)),
            self.clean,
        )

    def test_text_layers_cannot_cross_final_offer_or_rescan_boundary(self):
        # A /Font check alone misses OCR operators without an explicit font.
        for overlay in (
            b"BT /F1 12 Tf 0 0 Td (OCR-REINTRODUCED) Tj ET\n",
            b"/Artifact BMC BT (OCR-INVISIBLE) Tj ET EMC\n",
            b"q 1 0 0 1 0 0 cm /Im0 Do Q\n",
        ):
            with self.subTest(overlay=overlay[:32]):
                changed = post_ocr_copy(self.clean, overlay=overlay)
                self.assertIn(overlay, PdfReader(BytesIO(changed)).pages[0][
                    "/Contents"].get_object().get_data())
                self.assertFalse(copies._passive_pages(changed, 1))
                self.assertIsNone(verified_generated_pdf_bytes(
                    copies.SanitizedCopyOffer(changed, 1)))

    def test_ocr_reintroduced_actions_are_always_denied(self):
        for active_feature in ("javascript", "openAction", "annotation", "attachment"):
            with self.subTest(feature=active_feature):
                altered = post_ocr_copy(self.clean, active_feature=active_feature)
                self.assertFalse(copies._passive_pages(altered, 1))
                self.assertIsNone(verified_generated_pdf_bytes(
                    copies.SanitizedCopyOffer(altered, 1)))

    def test_pre_rebuild_ocr_content_is_discarded_with_actions(self):
        injected = post_ocr_copy(
            self.clean,
            overlay=b"BT (OCR-REINTRODUCED) Tj ET\n",
            active_feature="javascript",
        )
        rebuilt = remove_active_pdf_functionality(injected, 1)
        self.assertIsNotNone(rebuilt)
        self.assertTrue(copies._passive_pages(rebuilt, 1))
        self.assertNotIn(b"OCR-REINTRODUCED", rebuilt)
        self.assertNotIn(b"OCR-injected script", rebuilt)
        reader = PdfReader(BytesIO(rebuilt), strict=True)
        self.assertEqual(reader.pages[0].extract_text(), "")
        self.assertNotIn("/Names", reader.trailer["/Root"])
        self.assertEqual(verified_generated_pdf_bytes(
            copies.SanitizedCopyOffer(rebuilt, 1)), rebuilt)

    def test_actual_offer_rebuilds_before_validation_even_if_converter_returns_ocr(self):
        injected = post_ocr_copy(
            self.clean,
            overlay=b"BT (OCR-REINTRODUCED) Tj ET\n",
            active_feature="openAction",
        )
        with (
            patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")),
            patch.object(copies, "run_limited_converter",
                         return_value=subprocess.CompletedProcess([], 0, injected)),
        ):
            offer = copies.offer_sanitized_pdf_copy(self.raster)
        self.assertIsNotNone(offer)
        self.assertNotIn(b"OCR-REINTRODUCED", offer.pdf_bytes)
        self.assertTrue(copies._passive_pages(offer.pdf_bytes, 1))
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertEqual(verified_generated_pdf_bytes(offer), offer.pdf_bytes)

    def test_installed_scanner_and_user_settings_untouched(self):
        root = Path(__file__).resolve().parent
        scanner = (root / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("maximum_sanitized_copy", scanner)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
