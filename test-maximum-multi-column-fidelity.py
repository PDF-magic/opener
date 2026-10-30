#!/usr/bin/env python3
"""opener-0517: regression tests for two-/three-column raster PDF fidelity.

Generated vector fixtures and pixel checks run on both CI platforms. The
macOS job alone performs actual CoreGraphics conversion and inspects its
returned raster-only PDF. No OCR, viewer launch or scanner policy changes.
"""

from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parent
PAGE_WIDTH = 420
PAGE_HEIGHT = 320
SCALE = 2
BASELINES = (214, 176)
HEADER_Y = 244
FOOTER_Y = 74
HEADER_HEIGHT = 30
FOOTER_HEIGHT = 20
RED = (217, 31, 31)
GREEN = (31, 166, 56)
BLUE = (31, 51, 217)

# Distinct two- and three-column pages with unique source text and visual bands.
LAYOUTS = (
    ((32, 154, RED, "LEFT TWO", "L2 ROW"),
     (234, 154, BLUE, "RIGHT TWO", "R2 ROW")),
    ((30, 94, RED, "LEFT THREE", "L3 ROW"),
     (163, 94, GREEN, "MIDDLE", "M3 ROW"),
     (296, 94, BLUE, "RIGHT THREE", "R3 ROW")),
)


def _pdf():
    writer = PdfWriter()
    for layout in LAYOUTS:
        page = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        font = writer._add_object(DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }))
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        instructions = []
        for start, width, color, first, second in layout:
            rgb = " ".join(f"{v / 255:.5f}" for v in color)
            for y, height in ((HEADER_Y, HEADER_HEIGHT),
                              (FOOTER_Y, FOOTER_HEIGHT)):
                instructions.append(
                    f"q {rgb} rg {start} {y} {width} {height} re f Q\n".encode("ascii")
                )
            for baseline, label in zip(BASELINES, (first, second)):
                instructions.append(
                    f"BT /F1 10 Tf 0 g 1 0 0 1 {start + 7} {baseline} Tm "
                    f"({label}) Tj ET\n".encode("ascii")
                )
        stream = DecodedStreamObject()
        stream.set_data(b"".join(instructions))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _pixel(image, x, y):
    return image.getpixel((round(x * SCALE), round((PAGE_HEIGHT - y) * SCALE)))[:3]


def _text_rect(start, width, baseline):
    return ((start + 6) * SCALE,
            (PAGE_HEIGHT - baseline - 13) * SCALE,
            (start + width - 6) * SCALE,
            (PAGE_HEIGHT - baseline + 4) * SCALE)


def _text_detail(image, region):
    gray = image.convert("L").crop(region)
    values = gray.load()
    ink = 0
    occupied = set()
    transitions = 0
    for y in range(gray.height):
        last = False
        for x in range(gray.width):
            dark = values[x, y] < 135
            if dark:
                ink += 1
                occupied.add(x)
            if dark != last:
                transitions += 1
            last = dark
    density = ink / (gray.width * gray.height)
    return (ink >= 55 and len(occupied) >= 22 and transitions >= 65
            and 0.004 < density < 0.28)


def _evidence(image, layout):
    if image.size != (PAGE_WIDTH * SCALE, PAGE_HEIGHT * SCALE):
        return {"bands": 0, "textRows": 0, "whiteGutters": 0, "whiteMargins": 0}
    image = image.convert("RGB")
    bands = 0
    rows = 0
    for start, width, color, _, _ in layout:
        for center in (HEADER_Y + HEADER_HEIGHT / 2,
                       FOOTER_Y + FOOTER_HEIGHT / 2):
            pixel = _pixel(image, start + width / 2, center)
            bands += sum(abs(a - b) for a, b in zip(pixel, color)) < 80
        for baseline in BASELINES:
            rows += _text_detail(image, _text_rect(start, width, baseline))
    gutters = 0
    for left, right in zip(layout, layout[1:]):
        x = (left[0] + left[1] + right[0]) / 2
        for y in (259, 214, 176, 84):
            gutters += min(_pixel(image, x, y)) >= 230
    margins = sum(min(_pixel(image, x, y)) >= 230
                  for x, y in ((12, 259), (PAGE_WIDTH - 12, 84)))
    return {"bands": bands, "textRows": rows,
            "whiteGutters": gutters, "whiteMargins": margins}


def _preserves_columns(evidence, count):
    return evidence == {
        "bands": 2 * count,
        "textRows": 2 * count,
        "whiteGutters": 4 * (count - 1),
        "whiteMargins": 2,
    }


def _reference_image(layout, *, include_text=True):
    """Metric-only proxy; actual conversion assertions use returned PDF."""
    image = Image.new("RGB", (PAGE_WIDTH * SCALE, PAGE_HEIGHT * SCALE), "white")
    draw = ImageDraw.Draw(image)
    for start, width, color, _, _ in layout:
        for y, height in ((HEADER_Y, HEADER_HEIGHT),
                          (FOOTER_Y, FOOTER_HEIGHT)):
            box = (start * SCALE,
                   (PAGE_HEIGHT - y - height) * SCALE,
                   (start + width) * SCALE - 1,
                   (PAGE_HEIGHT - y) * SCALE - 1)
            draw.rectangle(box, fill=color)
        if include_text:
            for baseline in BASELINES:
                box = _text_rect(start, width, baseline)
                draw.text((box[0] + 4, box[1] + 4), "ABC 123 READ", fill="black")
    return image


class MultiColumnFixtureTests(unittest.TestCase):
    def test_source_contains_two_and_three_independent_text_columns(self):
        reader = PdfReader(BytesIO(_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, (page, layout) in enumerate(zip(reader.pages, LAYOUTS)):
            with self.subTest(page=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)),
                                 (PAGE_WIDTH, PAGE_HEIGHT))
                text = page.extract_text()
                for _, _, _, first, second in layout:
                    self.assertIn(first, text)
                    self.assertIn(second, text)
                self.assertEqual(len(page.images), 0)

    def test_pixel_metric_detects_missing_columns_ink_and_gutter_bleed(self):
        for index, layout in enumerate(LAYOUTS):
            with self.subTest(page=index):
                reference = _reference_image(layout)
                self.assertTrue(_preserves_columns(
                    _evidence(reference, layout), len(layout)
                ))
                blank = Image.new("RGB", reference.size, "white")
                self.assertFalse(_preserves_columns(_evidence(blank, layout), len(layout)))
                no_text = _reference_image(layout, include_text=False)
                self.assertFalse(_preserves_columns(
                    _evidence(no_text, layout), len(layout)
                ))
                shifted = Image.new("RGB", reference.size, "white")
                shifted.paste(reference.crop((40, 0, reference.width, reference.height)),
                              (0, 0))
                self.assertFalse(_preserves_columns(_evidence(shifted, layout), len(layout)))
                bridged = reference.copy()
                left, right = layout[:2]
                midpoint = (left[0] + left[1] + right[0]) / 2
                draw = ImageDraw.Draw(bridged)
                draw.rectangle((int(midpoint * SCALE - 5),
                                int((PAGE_HEIGHT - 259) * SCALE - 5),
                                int(midpoint * SCALE + 5),
                                int((PAGE_HEIGHT - 259) * SCALE + 5)),
                               fill="black")
                self.assertFalse(_preserves_columns(_evidence(bridged, layout), len(layout)))

    def test_optional_converter_and_deployed_scanner_remain_unchanged(self):
        scan = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("maximum-multi-column-fidelity", scan)
        self.assertIn("if not cached_clean(cache_id):", scan)
        self.assertIn("python3 test-maximum-multi-column-fidelity.py -v", workflow)
        from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        self.assertTrue(copies.SanitizedCopyOffer(_pdf(), 2).needs_separate_scan)


@unittest.skipUnless(sys.platform == "darwin", "CoreGraphics conversion requires macOS")
class NativeMultiColumnFidelityTests(unittest.TestCase):
    def test_real_sanitized_copy_preserves_two_and_three_column_layout(self):
        source = _pdf()
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offer, "CoreGraphics must produce a raster-only copy")
        self.assertNotEqual(offer.pdf_bytes, source)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.rasterized)
        self.assertTrue(offer.needs_separate_scan)
        reader = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, (page, layout) in enumerate(zip(reader.pages, LAYOUTS)):
            with self.subTest(page=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)),
                                 (PAGE_WIDTH, PAGE_HEIGHT))
                self.assertEqual((page.extract_text() or "").strip(), "")
                images = list(page.images)
                self.assertEqual(len(images), 1)
                with Image.open(BytesIO(images[0].data)) as rendered:
                    self.assertEqual(rendered.size,
                                     (PAGE_WIDTH * SCALE, PAGE_HEIGHT * SCALE))
                    evidence = _evidence(rendered, layout)
                    self.assertTrue(_preserves_columns(evidence, len(layout)),
                                    f"Converted page {index + 1} lost columns: {evidence}")


if __name__ == "__main__":
    unittest.main()
