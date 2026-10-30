#!/usr/bin/env python3
"""opener-0518: verify fidelity of full-page image-only scanned PDFs.

Linux exercises synthetic scan fixtures and pixel-metric negative controls;
macOS additionally converts the actual pages with CoreGraphics and checks the
resulting PDF. The original and generated PDFs stay in memory. No OCR is used.
"""

from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject, NumberObject

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parents[2]
PAGE_WIDTH, PAGE_HEIGHT = 240, 320
RENDER_SCALE = 2
PAPER = (244, 244, 244)


def _scan_page(index):
    """Make two distinct printouts already scanned to one full-page bitmap."""
    if index not in (0, 1):
        raise ValueError("Only two reference scan pages are supported")
    image = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), PAPER)
    draw = ImageDraw.Draw(image)
    ink = (27, 27, 27)
    for x in (11, PAGE_WIDTH - 12):
        for y in (11, PAGE_HEIGHT - 12):
            draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=ink)
            draw.rectangle((x - 1, y - 5, x + 1, y + 5), fill=ink)
    draw.rectangle((23, 35, PAGE_WIDTH - 24, 54), fill=(207, 207, 207))
    draw.text((31, 39), f"SCAN SHEET {index + 1}", fill=ink)
    for row in range(15):
        y = 76 + row * 13
        # Fine 1px rules and printed glyphs must survive; all ink is raster
        # pixels, never a searchable PDF text object or an OCR layer.
        draw.line((27, y + 9, 211, y + 9), fill=(177, 177, 177), width=1)
        draw.text((30 + (row % 3) * 4, y),
                  f"ITEM {index + 1}-{row + 1:02d}  1234", fill=ink)
    draw.rectangle((25, 276, 99, 295), fill=(171, 171, 171))
    for x in range(28, 98, 5):
        for y in range(278, 294, 5):
            draw.point((x, y), fill=(40, 40, 40))
    if index == 0:
        draw.rectangle((137, 273, 211, 298), outline=(38, 38, 38), width=2)
        draw.text((143, 282), "GRAY 01", fill=(44, 44, 44))
    else:
        draw.rectangle((131, 269, 215, 301), fill=(177, 222, 237),
                       outline=(19, 92, 165), width=2)
        draw.text((140, 278), "BLUE 02", fill=(12, 61, 123))
        draw.line((137, 294, 211, 294), fill=(186, 40, 45), width=3)
        draw.rectangle((166, 38, 208, 51), fill=(193, 51, 46))
    return image


def _source_pdf():
    """Place one Flate-compressed bitmap XObject over each entire page."""
    writer = PdfWriter()
    for index in range(2):
        page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        raw = DecodedStreamObject()
        raw.set_data(_scan_page(index).tobytes())
        image = raw.flate_encode()
        image.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(PAGE_WIDTH),
            NameObject("/Height"): NumberObject(PAGE_HEIGHT),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/XObject"): DictionaryObject({
                NameObject("/Scan"): writer._add_object(image),
            }),
        })
        instructions = DecodedStreamObject()
        instructions.set_data((
            f"q {PAGE_WIDTH} 0 0 {PAGE_HEIGHT} 0 0 cm /Scan Do Q\n"
        ).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(instructions)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _scan_evidence(candidate, reference):
    """Pixel-only legibility proxy: no OCR and no private document text."""
    if candidate.size != reference.size:
        return {"meanError": 255.0, "darkMean": 255.0, "lightMean": 0.0,
                "cornerMarks": 0, "landmarkError": 255.0}
    candidate = candidate.convert("RGB")
    reference = reference.convert("RGB")
    mean_error = sum(ImageStat.Stat(
        ImageChops.difference(candidate, reference)
    ).mean) / 3
    # Local registration differentiates similar scanned sheets where broad
    # full-page averages alone could conceal a page-order regression.
    landmark = (125, 266, 218, 304)
    landmark_error = sum(ImageStat.Stat(ImageChops.difference(
        candidate.crop(landmark), reference.crop(landmark)
    )).mean) / 3
    cand = candidate.convert("L")
    source = reference.convert("L")
    dark, light = [], []
    for y in range(33, PAGE_HEIGHT - 14, 2):
        for x in range(23, PAGE_WIDTH - 23, 2):
            actual = cand.getpixel((x, y))
            original = source.getpixel((x, y))
            if original < 95:
                dark.append(actual)
            elif original >= 234:
                light.append(actual)
    corners = sum(cand.getpixel((x, y)) < 115
                  for x in (11, PAGE_WIDTH - 12)
                  for y in (11, PAGE_HEIGHT - 12))
    return {"meanError": mean_error,
            "darkMean": sum(dark) / len(dark) if dark else 255.0,
            "lightMean": sum(light) / len(light) if light else 0.0,
            "cornerMarks": corners, "landmarkError": landmark_error}


def _preserves_scan(evidence):
    return (evidence["meanError"] < 22
            and evidence["landmarkError"] < 24
            and evidence["darkMean"] < 108
            and evidence["lightMean"] > 218
            and evidence["lightMean"] - evidence["darkMean"] > 120
            and evidence["cornerMarks"] == 4)


class ScannedDocumentFixtureTests(unittest.TestCase):
    def test_source_is_two_distinct_full_bleed_image_only_scans(self):
        reader = PdfReader(BytesIO(_source_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(page=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)),
                                 (PAGE_WIDTH, PAGE_HEIGHT))
                self.assertEqual((page.extract_text() or "").strip(), "")
                self.assertEqual(len(page.images), 1)
                with Image.open(BytesIO(page.images[0].data)) as image:
                    self.assertEqual(image.convert("RGB").tobytes(),
                                     _scan_page(index).tobytes())
        self.assertNotEqual(_scan_page(0).tobytes(), _scan_page(1).tobytes())

    def test_pixel_metric_rejects_blank_blurred_thumbnails_swapped_and_cropped_scans(self):
        for index in range(2):
            with self.subTest(page=index):
                reference = _scan_page(index)
                self.assertTrue(_preserves_scan(_scan_evidence(reference, reference)))
                white = Image.new("RGB", reference.size, "white")
                clipped = white.copy()
                clipped.paste(
                    reference.crop((12, 0, PAGE_WIDTH, PAGE_HEIGHT)), (0, 0)
                )
                degraded = (
                    white,
                    reference.filter(ImageFilter.GaussianBlur(radius=4)),
                    Image.blend(reference, white, 0.8),
                    reference.resize((48, 64), Image.Resampling.BOX).resize(
                        reference.size, Image.Resampling.BILINEAR),
                    _scan_page(1 - index),
                    clipped,
                )
                for altered in degraded:
                    self.assertFalse(
                        _preserves_scan(_scan_evidence(altered, reference)),
                        f"Missing scan regression on page {index + 1}",
                    )

    def test_only_checks_optional_output_not_clamav_or_user_preferences(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/consolidated-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("maximum-scanned-documents", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertEqual(workflow.count(
            "python3 tests/maximum/scanned-documents.py -v"), 2)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        offer = copies.SanitizedCopyOffer(_source_pdf(), 2)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)


@unittest.skipUnless(sys.platform == "darwin", "CoreGraphics conversion requires macOS")
class NativeScannedDocumentFidelityTests(unittest.TestCase):
    def test_real_conversion_keeps_scanned_pages_legible_and_in_order(self):
        source = _source_pdf()
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offer, "Real CoreGraphics converter must return sanitized bytes")
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)
        self.assertNotEqual(offer.pdf_bytes, source)
        reader = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(page=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)),
                                 (PAGE_WIDTH, PAGE_HEIGHT))
                self.assertEqual((page.extract_text() or "").strip(), "")
                images = list(page.images)
                self.assertEqual(len(images), 1)
                with Image.open(BytesIO(images[0].data)) as rendered:
                    self.assertEqual(rendered.size,
                                     (PAGE_WIDTH * RENDER_SCALE,
                                      PAGE_HEIGHT * RENDER_SCALE))
                    scanned = rendered.convert("RGB").resize(
                        (PAGE_WIDTH, PAGE_HEIGHT), Image.Resampling.BOX)
                    evidence = _scan_evidence(scanned, _scan_page(index))
                    self.assertTrue(_preserves_scan(evidence),
                                    f"Converted page {index + 1} degraded: {evidence}")
                    swapped = _scan_evidence(scanned, _scan_page(1 - index))
                    self.assertFalse(_preserves_scan(swapped),
                                     "Distinct scanned pages must not be swapped")


if __name__ == "__main__":
    unittest.main()
