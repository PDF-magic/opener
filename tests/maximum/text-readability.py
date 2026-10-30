#!/usr/bin/env python3
"""opener-0515: check visual text fidelity of Maximum's rasterized PDF copy.

The native macOS test uses generated, harmless PDF glyphs. Pixel measurements
are conservative legibility proxies, not OCR or a guarantee of accessibility.
This suite never opens a viewer, removes quarantine, or approves a scan.
"""

from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw, ImageFilter
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parents[2]
PAGE_WIDTH = 360
PAGE_HEIGHT = 260
RENDER_SCALE = 2

# Deliberately exercise small body text, normal body text, and larger heading.
TEXT_ROWS = (
    (8, 218, "Small 8pt text ABCDE 012345 XYZ"),
    (10, 168, "Medium 10pt readable 01234567"),
    (14, 108, "Heading 14pt clarity 123ABC"),
)
SECOND_PAGE = (10, 155, "Second page readable text 56789")


def _synthetic_text_pdf():
    """Construct deterministic vector text in memory with a standard PDF font."""
    writer = PdfWriter()
    for rows in (TEXT_ROWS, (SECOND_PAGE,)):
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
        for size, baseline, text in rows:
            instructions.append(
                f"BT /F1 {size} Tf 0 g 1 0 0 1 28 {baseline} Tm "
                f"({text}) Tj ET\n".encode("ascii")
            )
        stream = DecodedStreamObject()
        stream.set_data(b"".join(instructions))
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _text_region(font_size, baseline):
    """Map a known PDF text baseline into a 2x raster-image crop."""
    top = PAGE_HEIGHT - (baseline + font_size + 5)
    bottom = PAGE_HEIGHT - (baseline - 5)
    return (26 * RENDER_SCALE, top * RENDER_SCALE,
            300 * RENDER_SCALE, bottom * RENDER_SCALE)


def _ink_evidence(image, rectangle):
    """Measure ink coverage and horizontal glyph transitions without OCR.

    This metric catches dropped text, washed-out text and heavily blurred
    glyphs, and rejects solid blocks that happen to occupy a text region.
    It is not used for production document admission.
    """
    region = image.convert("L").crop(rectangle)
    values = region.load()
    width, height = region.size
    black = 0
    ink_columns = set()
    transitions = 0
    for y in range(height):
        previous = False
        for x in range(width):
            current = values[x, y] < 135
            if current:
                black += 1
                ink_columns.add(x)
            if current != previous:
                transitions += 1
            previous = current
    proportion = black / (width * height)
    return {
        "blackPixels": black,
        "inkColumns": len(ink_columns),
        "horizontalTransitions": transitions,
        "inkFraction": proportion,
    }


def _has_readable_glyph_detail(evidence):
    return (
        evidence["blackPixels"] >= 90
        and evidence["inkColumns"] >= 45
        and evidence["horizontalTransitions"] >= 90
        and 0.005 < evidence["inkFraction"] < 0.30
    )


class TextFidelityMetricTests(unittest.TestCase):
    def test_metric_distinguishes_ink_detail_from_lost_or_degraded_text(self):
        canvas = Image.new("RGB", (300, 64), "white")
        ImageDraw.Draw(canvas).text(
            (20, 12), "Readable text sample 0123456789 ABC", fill="black"
        )
        rectangle = (10, 5, 285, 45)
        self.assertTrue(_has_readable_glyph_detail(_ink_evidence(canvas, rectangle)))
        self.assertFalse(_has_readable_glyph_detail(_ink_evidence(
            Image.new("RGB", canvas.size, "white"), rectangle
        )))
        self.assertFalse(_has_readable_glyph_detail(_ink_evidence(
            canvas.filter(ImageFilter.GaussianBlur(4)), rectangle
        )))
        self.assertFalse(_has_readable_glyph_detail(_ink_evidence(
            Image.blend(canvas, Image.new("RGB", canvas.size, "white"), 0.82),
            rectangle,
        )))
        solid = Image.new("RGB", canvas.size, "white")
        ImageDraw.Draw(solid).rectangle((20, 12, 280, 30), fill="black")
        self.assertFalse(_has_readable_glyph_detail(_ink_evidence(solid, rectangle)))

    def test_text_fixture_contains_expected_source_text(self):
        reader = PdfReader(BytesIO(_synthetic_text_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for page, rows in zip(reader.pages, (TEXT_ROWS, (SECOND_PAGE,))):
            text = page.extract_text()
            for _, _, expected in rows:
                self.assertIn(expected, text)

    def test_sanitizer_gates_are_unmodified(self):
        # The text checks are CI-only diagnostics, not an opening policy.
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("maximum-text-readability", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        self.assertTrue(copies.SanitizedCopyOffer(_synthetic_text_pdf(), 2).needs_separate_scan)


@unittest.skipUnless(sys.platform == "darwin", "CoreGraphics conversion requires macOS")
class NativeTextReadabilityTests(unittest.TestCase):
    def test_text_remains_legible_after_real_two_page_conversion(self):
        source = _synthetic_text_pdf()
        attempt = copies.attempt_sanitized_pdf_copy(source)
        self.assertIsNotNone(
            attempt.offer,
            "Native conversion failure category: " +
            (attempt.failure.kind.value if attempt.failure else "unknown"),
        )
        offer = attempt.offer
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)
        self.assertNotEqual(offer.pdf_bytes, source)
        output = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(output.pages), 2)
        for page_index, rows in enumerate((TEXT_ROWS, (SECOND_PAGE,))):
            page = output.pages[page_index]
            self.assertEqual((float(page.mediabox.width), float(page.mediabox.height)),
                             (PAGE_WIDTH, PAGE_HEIGHT))
            self.assertEqual((page.extract_text() or "").strip(), "")
            images = list(page.images)
            self.assertEqual(len(images), 1)
            with Image.open(BytesIO(images[0].data)) as image:
                self.assertEqual(image.size, (PAGE_WIDTH * RENDER_SCALE,
                                              PAGE_HEIGHT * RENDER_SCALE))
                for size, baseline, text in rows:
                    with self.subTest(page=page_index, fontSize=size, text=text):
                        evidence = _ink_evidence(image, _text_region(size, baseline))
                        self.assertTrue(
                            _has_readable_glyph_detail(evidence),
                            f"Raster copy lost visible {size}pt glyph details: {evidence}",
                        )


if __name__ == "__main__":
    unittest.main()
