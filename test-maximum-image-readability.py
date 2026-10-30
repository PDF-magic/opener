#!/usr/bin/env python3
"""opener-0516: verify embedded pictures remain visually readable after rasterization.

Fixture and metric checks run on Linux and macOS. Only the macOS job calls
the real CoreGraphics converter and evaluates the actual returned PDF images.
Metrics are CI-only fidelity proxies, never scanner admission decisions.
"""

from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
)

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parent
PAGE_WIDTH, PAGE_HEIGHT = 200, 160
IMAGE_WIDTH, IMAGE_HEIGHT = 120, 84
IMAGE_X, IMAGE_Y = 28, 34
RENDER_SCALE = 2
# A source pixel occupies one PDF point and two output pixels. Inner crops
# avoid page-background and edge antialiasing when comparing image detail.
IMAGE_BOX = (
    IMAGE_X * RENDER_SCALE,
    (PAGE_HEIGHT - IMAGE_Y - IMAGE_HEIGHT) * RENDER_SCALE,
    (IMAGE_X + IMAGE_WIDTH) * RENDER_SCALE,
    (PAGE_HEIGHT - IMAGE_Y) * RENDER_SCALE,
)


def _picture(page_index):
    """Synthetic color diagram with readable fine lines and a 6px checker grid."""
    if page_index not in (0, 1):
        raise ValueError("Only deterministic fixture pages are supported")
    picture = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), "white")
    draw = ImageDraw.Draw(picture)
    palettes = (
        ((225, 35, 40), (25, 190, 65), (35, 60, 220)),
        ((30, 185, 215), (205, 55, 195), (225, 180, 25)),
    )
    for index, color in enumerate(palettes[page_index]):
        draw.rectangle((index * 40, 0, index * 40 + 39, 21), fill=color)
    # High-contrast alternating cells test whether visual symbols survive.
    for row in range(7):
        for column in range(20):
            shade = 15 if (row + column + page_index) % 2 else 245
            draw.rectangle(
                (column * 6, 24 + row * 6,
                 column * 6 + 5, 24 + row * 6 + 5),
                fill=(shade, shade, shade),
            )
    # One-pixel diagram strokes are deliberately fragile under severe blur.
    for column in range(0, IMAGE_WIDTH, 6):
        draw.line((column, 70, column, 82), fill=(15, 15, 15), width=1)
    return picture


def _source_pdf():
    """Embed real Flate-compressed RGB image XObjects in two PDF pages."""
    writer = PdfWriter()
    for page_index in range(2):
        page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        picture = _picture(page_index)
        stream = DecodedStreamObject()
        stream.set_data(picture.tobytes())
        encoded = stream.flate_encode()
        encoded.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(IMAGE_WIDTH),
            NameObject("/Height"): NumberObject(IMAGE_HEIGHT),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
        })
        image_ref = writer._add_object(encoded)
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/XObject"): DictionaryObject({
                NameObject("/Im0"): image_ref,
            }),
        })
        content = DecodedStreamObject()
        content.set_data((
            f"q {IMAGE_WIDTH} 0 0 {IMAGE_HEIGHT} "
            f"{IMAGE_X} {IMAGE_Y} cm /Im0 Do Q\n"
        ).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _readability_evidence(candidate, reference):
    """Bounded pixel-difference and checker-center evidence without OCR.

    Compare in source image coordinates after cropping the expected PDF
    placement. Wrong pages, blank or heavily blurred images cannot pass.
    """
    if candidate.size != reference.size:
        return {"meanError": 255.0, "darkMean": 255.0, "lightMean": 0.0}
    candidate = candidate.convert("RGB")
    reference = reference.convert("RGB")
    mean_error = sum(ImageStat.Stat(ImageChops.difference(
        candidate, reference
    )).mean) / 3
    grayscale = candidate.convert("L")
    dark, light = [], []
    for row in range(7):
        for column in range(20):
            x, y = 6 * column + 3, 24 + 6 * row + 3
            shade = grayscale.getpixel((x, y))
            expected_shade = reference.getpixel((x, y))[0]
            (dark if expected_shade < 100 else light).append(shade)
    return {
        "meanError": mean_error,
        "darkMean": sum(dark) / len(dark),
        "lightMean": sum(light) / len(light),
    }


def _image_is_readable(evidence):
    return (evidence["meanError"] < 32
            and evidence["darkMean"] < 95
            and evidence["lightMean"] > 170
            and evidence["lightMean"] - evidence["darkMean"] > 100)


class ImageReadabilityMetricTests(unittest.TestCase):
    def test_fixtures_embed_distinct_inert_image_pixels_on_both_pages(self):
        reader = PdfReader(BytesIO(_source_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(page=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)),
                                 (PAGE_WIDTH, PAGE_HEIGHT))
                self.assertEqual(len(page.images), 1)
                with Image.open(BytesIO(page.images[0].data)) as encoded:
                    self.assertEqual(encoded.convert("RGB").tobytes(),
                                     _picture(index).tobytes())
                self.assertEqual((page.extract_text() or "").strip(), "")

    def test_readability_metric_rejects_blank_blurred_faded_and_wrong_page(self):
        original = _picture(0)
        white = Image.new("RGB", original.size, "white")
        self.assertTrue(_image_is_readable(
            _readability_evidence(original, original)
        ))
        degraded = (
            white,
            original.filter(ImageFilter.GaussianBlur(5)),
            Image.blend(original, white, 0.85),
            Image.new("RGB", original.size, (125, 125, 125)),
            _picture(1),
        )
        for image in degraded:
            with self.subTest(kind=image.getpixel((2, 2))):
                self.assertFalse(_image_is_readable(
                    _readability_evidence(image, original)
                ))
        self.assertFalse(_image_is_readable(
            _readability_evidence(
                Image.new("RGB", (60, 42), "white"), original
            )
        ))

    def test_is_a_fidelity_test_not_a_scanner_or_opening_control(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/consolidated-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("maximum-image-readability", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("python3 test-maximum-image-readability.py -v", workflow)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        self.assertTrue(copies.SanitizedCopyOffer(_source_pdf(), 2).needs_separate_scan)


@unittest.skipUnless(sys.platform == "darwin", "Real CoreGraphics conversion requires macOS")
class NativeImageReadabilityTests(unittest.TestCase):
    def test_two_embedded_pictures_remain_readable_after_real_conversion(self):
        source = _source_pdf()
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offer, "Native image conversion must produce a raster-only copy")
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
                    self.assertEqual(
                        rendered.size,
                        (PAGE_WIDTH * RENDER_SCALE, PAGE_HEIGHT * RENDER_SCALE)
                    )
                    crop = rendered.convert("RGB").crop(IMAGE_BOX).resize(
                        (IMAGE_WIDTH, IMAGE_HEIGHT),
                        Image.Resampling.BOX
                    )
                    expected = _picture(index)
                    evidence = _readability_evidence(crop, expected)
                    self.assertTrue(
                        _image_is_readable(evidence),
                        f"Converted image on page {index + 1} lost detail: {evidence}"
                    )
                    wrong_page = _readability_evidence(crop, _picture(1 - index))
                    self.assertFalse(
                        _image_is_readable(wrong_page),
                        f"Converted images may have been swapped: {wrong_page}"
                    )


if __name__ == "__main__":
    unittest.main()
