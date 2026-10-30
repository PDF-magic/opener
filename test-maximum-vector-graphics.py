#!/usr/bin/env python3
"""opener-0519: vector path fidelity through optional Maximum rasterization.

Linux checks deterministic vector-only PDF fixtures and independent pixel
metrics. macOS also runs the real CoreGraphics sanitizer and validates its
raster-only PDF output; no mocked conversion can satisfy the native test.
"""
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parent
PAGE_WIDTH, PAGE_HEIGHT, SCALE = 320, 240, 2
RED, GREEN, BLUE = (210, 30, 35), (35, 168, 53), (30, 85, 220)
PURPLE, ORANGE, TEAL = (169, 53, 190), (231, 126, 25), (24, 163, 175)
MAGENTA, NAVY = (211, 28, 132), (34, 55, 115)


def _rgb(color):
    return " ".join(f"{item / 255:.6f}" for item in color)


def _pdf():
    """Both pages contain only stroked, filled and clipped PDF vector paths."""
    instructions = (
        (
            f"q {_rgb(RED)} rg 24 153 80 55 re f Q\n"
            f"q {_rgb(GREEN)} rg 33 45 m 105 45 l 68 116 l h f Q\n"
            f"q {_rgb(BLUE)} RG 4 w 130 200 m 172 228 220 137 272 184 c S Q\n"
            f"q 0 0 0 RG 3 w 157 45 m 264 125 l S Q\n"
            f"q 0.5 G 1 w 132 140 m 276 140 l S Q\n"
            f"q 221 25 57 55 re W n {_rgb(PURPLE)} rg 196 9 105 87 re f Q\n"
        ),
        (
            f"q {_rgb(ORANGE)} rg 75 210 m 93.75 210 109 194.75 109 176 c "
            f"109 157.25 93.75 142 75 142 c 56.25 142 41 157.25 41 176 c "
            f"41 194.75 56.25 210 75 210 c f Q\n"
            f"q {_rgb(TEAL)} rg 160 157 110 51 re f Q\n"
            f"q {_rgb(MAGENTA)} RG 5 w 34 58 m 74 111 l 124 61 l S Q\n"
            f"q {_rgb(NAVY)} RG 2 w 160 40 m 272 40 l 272 112 l 160 112 l h S Q\n"
            f"q {_rgb(BLUE)} rg 179 140 m 207 125 l 179 110 l 151 125 l h f Q\n"
        ),
    )
    writer = PdfWriter()
    for operators in instructions:
        page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        stream = DecodedStreamObject()
        stream.set_data(operators.encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    sink = BytesIO()
    writer.write(sink)
    return sink.getvalue()


def _point(x, y):
    return round(x * SCALE), round((PAGE_HEIGHT - y) * SCALE)


def _rect(x0, y0, x1, y1):
    return (_point(x0, y1)[0], _point(x0, y1)[1],
            _point(x1, y0)[0], _point(x1, y0)[1])


def _cubic(p0, p1, p2, p3):
    points = []
    for step in range(81):
        t = step / 80
        u = 1 - t
        x = u**3*p0[0] + 3*u*u*t*p1[0] + 3*u*t*t*p2[0] + t**3*p3[0]
        y = u**3*p0[1] + 3*u*u*t*p1[1] + 3*u*t*t*p2[1] + t**3*p3[1]
        points.append(_point(x, y))
    return points


def _reference_image(index):
    """Independent Pillow drawing checks pixel metrics on all CI platforms."""
    image = Image.new("RGB", (PAGE_WIDTH*SCALE, PAGE_HEIGHT*SCALE), "white")
    draw = ImageDraw.Draw(image)
    if index == 0:
        draw.rectangle(_rect(24, 153, 104, 208), fill=RED)
        draw.polygon([_point(*p) for p in ((33, 45), (105, 45), (68, 116))],
                     fill=GREEN)
        draw.line(_cubic((130, 200), (172, 228), (220, 137), (272, 184)),
                  fill=BLUE, width=8)
        draw.line((_point(157, 45), _point(264, 125)), fill=(0, 0, 0), width=6)
        draw.line((_point(132, 140), _point(276, 140)),
                  fill=(128, 128, 128), width=2)
        draw.rectangle(_rect(221, 25, 278, 80), fill=PURPLE)
    else:
        draw.ellipse(_rect(41, 142, 109, 210), fill=ORANGE)
        draw.rectangle(_rect(160, 157, 270, 208), fill=TEAL)
        draw.line([_point(*p) for p in ((34, 58), (74, 111), (124, 61))],
                  fill=MAGENTA, width=10, joint="curve")
        draw.line([_point(*p) for p in
                   ((160, 40), (272, 40), (272, 112), (160, 112), (160, 40))],
                  fill=NAVY, width=4)
        draw.polygon([_point(*p) for p in
                      ((179, 140), (207, 125), (179, 110), (151, 125))],
                     fill=BLUE)
    return image


# Independent landmarks for separate nonoverlapping geometric features.
FEATURE_REGIONS = (
    ((RED, (24, 153, 104, 208), 900),
     (GREEN, (33, 45, 105, 116), 600),
     (BLUE, (128, 150, 277, 228), 170),
     (PURPLE, (221, 25, 278, 80), 900)),
    ((ORANGE, (41, 142, 109, 210), 900),
     (TEAL, (160, 157, 270, 208), 900),
     (MAGENTA, (30, 53, 128, 117), 250),
     (NAVY, (157, 37, 276, 116), 250),
     (BLUE, (150, 108, 209, 142), 250)),
)


def _color_count(image, region, color):
    pixels = image.crop(_rect(*region)).convert("RGB").getdata()
    return sum(max(abs(a-b) for a, b in zip(pixel, color)) <= 47
               for pixel in pixels)


def _white_at(image, x, y):
    return min(image.convert("RGB").getpixel(_point(x, y))) >= 224


def _near_color(image, x, y, color):
    pixel = image.convert("RGB").getpixel(_point(x, y))
    return max(abs(a-b) for a, b in zip(pixel, color)) <= 47


def _vector_evidence(image, index):
    """Geometry, color, strokes and clipping; do not use OCR or PDF text."""
    if image.size != (PAGE_WIDTH*SCALE, PAGE_HEIGHT*SCALE):
        return {"landmarks": 0, "background": False, "detail": False}
    image = image.convert("RGB")
    matches = sum(_color_count(image, box, color) >= minimum
                  for color, box, minimum in FEATURE_REGIONS[index])
    background = all(_white_at(image, x, y) for x, y in
                     ((8, 15), (310, 220), (145, 232), (196, 34)))
    if index == 0:
        # Keep the thin rule and diagonal, not merely filled color blocks.
        diagonal = sum(max(image.getpixel(_point(
            x, 45+(x-157)*80/107))) < 90 for x in (165, 185, 215, 245, 258))
        gray = sum(max(image.getpixel(_point(x, 140))) < 185
                   for x in range(140, 268, 5))
        detail = (diagonal >= 3 and gray >= 15
                  and _near_color(image, 98, 180, RED)
                  and _near_color(image, 270, 55, PURPLE))
    else:
        detail = (
            all(_white_at(image, x, y) for x, y in ((180, 96), (178, 70)))
            and _near_color(image, 258, 182, TEAL)
            and _near_color(image, 88, 181, ORANGE)
        )
    return {"landmarks": matches, "background": background, "detail": detail}


def _preserves_vectors(evidence, index):
    return (evidence["landmarks"] == len(FEATURE_REGIONS[index])
            and evidence["background"] and evidence["detail"])


class VectorFixtureTests(unittest.TestCase):
    def test_source_has_two_distinct_raster_free_vector_pages(self):
        reader = PdfReader(BytesIO(_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(index=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)),
                                 (PAGE_WIDTH, PAGE_HEIGHT))
                self.assertEqual((page.extract_text() or "").strip(), "")
                self.assertEqual(len(page.images), 0)
                data = page.get_contents().get_data()
                self.assertIn(b" m ", data)
                self.assertIn(b" f Q", data)
                self.assertIn(b" S Q", data)
                if index == 0:
                    self.assertIn(b" c S Q", data)
                    self.assertIn(b" re W n ", data)
                else:
                    self.assertIn(b" c f Q", data)
        self.assertNotEqual(reader.pages[0].get_contents().get_data(),
                            reader.pages[1].get_contents().get_data())

    def test_vector_metrics_reject_missing_shapes_shift_page_swaps_and_clip_leaks(self):
        for index in (0, 1):
            with self.subTest(index=index):
                original = _reference_image(index)
                self.assertTrue(_preserves_vectors(
                    _vector_evidence(original, index), index))
                blank = Image.new("RGB", original.size, "white")
                missing = original.copy()
                ImageDraw.Draw(missing).rectangle(
                    _rect(*FEATURE_REGIONS[index][0][1]), fill="white")
                shifted = blank.copy()
                shifted.paste(original.crop(
                    (48, 0, original.width, original.height)), (0, 0))
                leaked = original.copy()
                ImageDraw.Draw(leaked).rectangle(
                    _rect(188, 24, 207, 44), fill="black")
                for altered in (
                    blank, missing, shifted, leaked, _reference_image(1-index)
                ):
                    self.assertFalse(_preserves_vectors(
                        _vector_evidence(altered, index), index))

    def test_optional_sanitizer_and_installed_scanner_are_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (
            ROOT / ".github/workflows/ci.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("maximum-vector-graphics", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertEqual(
            workflow.count("python3 test-maximum-vector-graphics.py -v"), 2)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        offer = copies.SanitizedCopyOffer(_pdf(), 2)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)


@unittest.skipUnless(sys.platform == "darwin", "CoreGraphics requires macOS")
class NativeVectorFidelityTests(unittest.TestCase):
    def test_real_conversion_preserves_path_geometry_colors_and_clipping(self):
        source = _pdf()
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(
            offer, "CoreGraphics must convert these synthetic vector pages")
        self.assertNotEqual(offer.pdf_bytes, source)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)
        reader = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(index=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)),
                                 (PAGE_WIDTH, PAGE_HEIGHT))
                self.assertEqual((page.extract_text() or "").strip(), "")
                images = list(page.images)
                self.assertEqual(len(images), 1)
                with Image.open(BytesIO(images[0].data)) as raster:
                    self.assertEqual(raster.size, (
                        PAGE_WIDTH*SCALE, PAGE_HEIGHT*SCALE))
                    evidence = _vector_evidence(raster.convert("RGB"), index)
                    self.assertTrue(_preserves_vectors(evidence, index),
                                    f"Converted vector page {index + 1}: {evidence}")
                    self.assertFalse(_preserves_vectors(
                        _vector_evidence(raster, 1-index), 1-index),
                        "Distinct vector pages may not be swapped")


if __name__ == "__main__":
    unittest.main()
