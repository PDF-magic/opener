#!/usr/bin/env python3
"""opener-0521: visual fidelity of rotated pages through Maximum sanitization.

Linux and macOS validate an asymmetric vector fixture and negative controls.
macOS additionally runs the actual CoreGraphics converter and checks pixels
from its fresh, raster-only output PDF; metadata-only rotation is not enough.
"""
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw, ImageOps
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, NumberObject

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parent
SCALE = 2
# Include 0/90/180/270, negative and inherited right-angle rotations.
# Each page is nonsquare so an accidental width/height exchange is observable.
PAGES = (
    (200, 280, 0),
    (210, 260, 90),
    (220, 280, 180),
    (240, 270, 270),
    (230, 290, -90),
    (250, 300, None),
)
NORMALIZED = (0, 90, 180, 270, 270, 90)
CORNERS = (
    (224, 35, 39),   # top-left red
    (30, 176, 66),   # top-right green
    (35, 76, 219),   # bottom-left blue
    (225, 180, 32),  # bottom-right yellow
)
CENTERS = (
    (149, 43, 187), (38, 185, 183), (28, 28, 28),
    (234, 112, 35), (202, 46, 124), (99, 77, 200),
)


def _rgb(color):
    return " ".join(f"{channel / 255:.6f}" for channel in color)


def _rectangles(index):
    width, height, _rotation = PAGES[index]
    markers = (
        (10, height - 42, 32, 32, CORNERS[0]),
        (width - 42, height - 42, 32, 32, CORNERS[1]),
        (10, 10, 32, 32, CORNERS[2]),
        (width - 42, 10, 32, 32, CORNERS[3]),
        (width // 2 - 14, height // 2 - 12, 28, 24, CENTERS[index]),
    )
    return markers


def _source_pdf():
    """Use PDF vector commands only; rotation is metadata, not baked pixels."""
    writer = PdfWriter()
    # Last page inherits /Rotate from /Pages; all other pages override it.
    writer._root_object["/Pages"].get_object()[NameObject("/Rotate")] = NumberObject(90)
    for index, (width, height, raw_rotation) in enumerate(PAGES):
        page = writer.add_blank_page(width=width, height=height)
        if raw_rotation is not None:
            page[NameObject("/Rotate")] = NumberObject(raw_rotation)
        instructions = "".join(
            f"q {_rgb(color)} rg {x} {y} {w} {h} re f Q\n"
            for x, y, w, h, color in _rectangles(index)
        )
        content = DecodedStreamObject()
        content.set_data(instructions.encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _reference(index):
    width, height, _ = PAGES[index]
    image = Image.new("RGB", (width * SCALE, height * SCALE), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for x, y, w, h, color in _rectangles(index):
        draw.rectangle((
            x * SCALE, (height - y - h) * SCALE,
            (x + w) * SCALE - 1, (height - y) * SCALE - 1,
        ), fill=color)
    return image


def _displayed(image, rotation):
    # Pillow ROTATE_270 is a clockwise quarter-turn, as PDF /Rotate 90.
    turns = {
        0: None, 90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }
    return image if rotation == 0 else image.transpose(turns[rotation])


def _sample(image, x, y):
    # Sample deeply inside each 32-point marker, avoiding antialiased edges.
    block = image.crop((x - 3, y - 3, x + 4, y + 4))
    pixels = list(block.getdata())
    return tuple(sum(pixel[channel] for pixel in pixels) // len(pixels)
                 for channel in range(3))


def _matches_expected(image, index, rotation):
    """Require orientation, unique center marker, corners, scale and margins."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    reference = _displayed(_reference(index), rotation)
    displayed = _displayed(image, rotation)
    if displayed.size != reference.size:
        return False

    width, height = reference.size
    # Centers of all corners and page-unique center, plus blank margins.
    samples = (
        (26 * SCALE, 26 * SCALE), (width - 26 * SCALE, 26 * SCALE),
        (26 * SCALE, height - 26 * SCALE),
        (width - 26 * SCALE, height - 26 * SCALE),
        (width // 2, height // 2), (4 * SCALE, height // 2),
        (width - 4 * SCALE, height // 2),
    )
    # Compare exact expected positions after the declared rotation, not
    # merely whether each color exists somewhere in the raster.
    return all(
        max(abs(a - b) for a, b in zip(_sample(displayed, x, y),
                                      _sample(reference, x, y))) <= 35
        for x, y in samples
    )


class RotatedPageFidelityTests(unittest.TestCase):
    def test_vector_source_has_six_nonsquare_pages_and_inherited_rotation(self):
        source = PdfReader(BytesIO(_source_pdf()), strict=True)
        self.assertEqual(len(source.pages), len(PAGES))
        for index, page in enumerate(source.pages):
            with self.subTest(index=index):
                width, height, rotation = PAGES[index]
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)), (width, height))
                self.assertEqual(int(page.get_inherited("/Rotate")) % 360,
                                 NORMALIZED[index])
                self.assertEqual(list(page.images), [])
                stream = page["/Contents"].get_object().get_data()
                self.assertEqual(stream.count(b" re f Q"), 5)
                self.assertTrue(_matches_expected(
                    _reference(index), index, NORMALIZED[index]
                ))
        self.assertEqual(
            int(source.pages[-1]["/Parent"].get_object()["/Rotate"]), 90
        )
        # pypdf may flatten inheritable /Rotate onto parsed leaf pages; the
        # effective orientation is the meaningful fidelity contract.
        self.assertEqual(int(source.pages[-1].get_inherited("/Rotate")), 90)

    def test_metric_rejects_wrong_rotation_mirrors_clipping_and_swapped_pages(self):
        for index in range(len(PAGES)):
            with self.subTest(index=index):
                image = _reference(index)
                rotation = NORMALIZED[index]
                self.assertTrue(_matches_expected(image, index, rotation))
                self.assertFalse(_matches_expected(
                    image.transpose(Image.Transpose.ROTATE_180), index, rotation
                ))
                self.assertFalse(_matches_expected(
                    ImageOps.mirror(image), index, rotation
                ))
                self.assertFalse(_matches_expected(
                    Image.new("RGB", image.size, "white"), index, rotation
                ))
                self.assertFalse(_matches_expected(
                    image.crop((0, 0, image.width - 30, image.height)),
                    index, rotation
                ))
                other = _reference((index + 1) % len(PAGES))
                self.assertFalse(_matches_expected(other, index, rotation))

    def test_copy_gate_and_saved_preferences_are_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("test-maximum-rotated-pages", scanner)
        self.assertIn("test-maximum-rotated-pages.py -v", workflow)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


@unittest.skipUnless(sys.platform == "darwin",
                     "Real CoreGraphics sanitized conversion requires macOS")
class NativeRotatedPageFidelityTests(unittest.TestCase):
    def test_real_conversion_preserves_visible_orientation_and_all_markers(self):
        source = _source_pdf()
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offer, "Supported rotated pages must convert")
        self.assertNotEqual(offer.pdf_bytes, source)
        self.assertEqual(offer.page_count, len(PAGES))
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)

        reader = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), len(PAGES))
        self.assertEqual(set(reader.trailer["/Root"]), {"/Type", "/Pages"})
        geometry = tuple((float(width), float(height), rotation)
                         for (width, height, _), rotation in zip(PAGES, NORMALIZED))
        self.assertTrue(copies._passive_pages(
            offer.pdf_bytes, len(PAGES), geometry
        ))

        for index, page in enumerate(reader.pages):
            with self.subTest(index=index, rotation=NORMALIZED[index]):
                width, height, _ = PAGES[index]
                self.assertEqual(
                    (float(page.mediabox.width), float(page.mediabox.height)),
                    (width, height)
                )
                self.assertEqual(int(page.get_inherited("/Rotate") or 0) % 360,
                                 NORMALIZED[index])
                self.assertNotIn("/Annots", page)
                self.assertEqual(page.extract_text().strip(), "")
                images = list(page.images)
                self.assertEqual(len(images), 1)
                with Image.open(BytesIO(images[0].data)) as image:
                    rendered = image.convert("RGB")
                self.assertEqual(rendered.size, (width * SCALE, height * SCALE))
                self.assertTrue(
                    _matches_expected(rendered, index, NORMALIZED[index]),
                    f"Page {index} rotation or visual corner markers changed",
                )
                display = _displayed(rendered, NORMALIZED[index])
                expected_display_size = (
                    (height * SCALE, width * SCALE)
                    if NORMALIZED[index] in (90, 270)
                    else (width * SCALE, height * SCALE)
                )
                self.assertEqual(display.size, expected_display_size)


if __name__ == "__main__":
    unittest.main()
