#!/usr/bin/env python3
"""opener-0520: verify PDF alpha, blend modes and soft-mask raster fidelity.

Both platforms validate source fixtures and independent pixel metrics;
macOS also checks actual CoreGraphics-converted, raster-only output.
"""
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, FloatObject,
    NameObject, NumberObject,
)

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT, SCALE = 240, 180, 2
BLUE = (30, 90, 210)
RED = (230, 40, 40)
TINT = (220, 30, 30)
YELLOW = (220, 194, 70)
BLEND_BLUE = (50, 85, 230)


def _rgb(color):
    return " ".join(f"{channel / 255:.7f}" for channel in color)


def _stream(writer, data):
    stream = DecodedStreamObject()
    stream.set_data(data.encode("ascii"))
    return writer._add_object(stream)


def _image_with_soft_mask(writer):
    """One 48x18 RGB XObject with 0%, 50% and 100% alpha stripes."""
    columns, rows = 48, 18
    mask = DecodedStreamObject()
    mask.set_data(bytes([alpha for _ in range(rows)
                         for alpha in ([0] * 16 + [128] * 16 + [255] * 16)]))
    mask.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(columns),
        NameObject("/Height"): NumberObject(rows),
        NameObject("/ColorSpace"): NameObject("/DeviceGray"),
        NameObject("/BitsPerComponent"): NumberObject(8),
    })
    smask_ref = writer._add_object(mask)
    image = DecodedStreamObject()
    image.set_data(bytes(TINT) * (columns * rows))
    image.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Image"),
        NameObject("/Width"): NumberObject(columns),
        NameObject("/Height"): NumberObject(rows),
        NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
        NameObject("/BitsPerComponent"): NumberObject(8),
        NameObject("/SMask"): smask_ref,
    })
    return writer._add_object(image)


def _pdf():
    writer = PdfWriter()
    for index in (0, 1):
        page = writer.add_blank_page(width=WIDTH, height=HEIGHT)
        state = DictionaryObject({
            NameObject("/Type"): NameObject("/ExtGState"),
            NameObject("/ca"): FloatObject(0.5),
            NameObject("/CA"): FloatObject(0.5),
        })
        if index == 1:
            state[NameObject("/BM")] = NameObject("/Multiply")
        name = "/Half" if index == 0 else "/MultiplyHalf"
        resources = DictionaryObject({
            NameObject("/ExtGState"): DictionaryObject({
                NameObject(name): writer._add_object(state),
            }),
        })
        if index == 0:
            resources[NameObject("/XObject")] = DictionaryObject({
                NameObject("/Tint"): _image_with_soft_mask(writer),
            })
            instructions = (
                f"q {_rgb(BLUE)} rg 20 45 110 95 re f Q\n"
                f"q /Half gs {_rgb(RED)} rg 80 45 110 95 re f Q\n"
                "q 72 0 0 27 32 10 cm /Tint Do Q\n"
            )
        else:
            instructions = (
                f"q {_rgb(YELLOW)} rg 20 45 135 95 re f Q\n"
                f"q /MultiplyHalf gs {_rgb(BLEND_BLUE)} rg "
                "90 45 100 95 re f Q\n"
            )
        page[NameObject("/Resources")] = resources
        page[NameObject("/Contents")] = _stream(writer, instructions)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _center(x, y):
    return round(x * SCALE), round((HEIGHT - y) * SCALE)


def _blend(background, foreground, alpha=0.5, mode="Normal"):
    if mode == "Multiply":
        foreground = tuple(round(a * b / 255)
                           for a, b in zip(background, foreground))
    return tuple(round(a * (1-alpha) + b * alpha)
                 for a, b in zip(background, foreground))


# Interior landmarks avoid antialiased edges and image-mask boundaries.
LANDMARKS = (
    (
        (45, 98, BLUE),
        (105, 98, _blend(BLUE, RED)),
        (173, 98, _blend((255, 255, 255), RED)),
        (219, 154, (255, 255, 255)),
        (44, 23, (255, 255, 255)),
        (68, 23, _blend((255, 255, 255), TINT, 128/255)),
        (92, 23, TINT),
    ),
    (
        (45, 98, YELLOW),
        (112, 98, _blend(YELLOW, BLEND_BLUE, mode="Multiply")),
        (174, 98, _blend((255, 255, 255), BLEND_BLUE, mode="Multiply")),
        (219, 154, (255, 255, 255)),
    ),
)


def _reference(index):
    """Independently compose expected opacity and PDF Multiply behavior."""
    image = Image.new("RGB", (WIDTH*SCALE, HEIGHT*SCALE), "white")

    def rectangle(box, color):
        x, y, width, height = box
        ImageDraw.Draw(image).rectangle(
            ((x*SCALE, (HEIGHT-y-height)*SCALE),
             ((x+width)*SCALE-1, (HEIGHT-y)*SCALE-1)), fill=color)

    def overlay(box, color, alpha=128, mode="Normal"):
        x, y, width, height = box
        for px in range(x*SCALE, (x+width)*SCALE):
            for py in range((HEIGHT-y-height)*SCALE, (HEIGHT-y)*SCALE):
                old = image.getpixel((px, py))
                image.putpixel((px, py), _blend(old, color, alpha/255, mode))

    if index == 0:
        rectangle((20, 45, 110, 95), BLUE)
        overlay((80, 45, 110, 95), RED)
        for section, alpha in enumerate((0, 128, 255)):
            overlay((32+section*24, 10, 24, 27), TINT, alpha=alpha)
    else:
        rectangle((20, 45, 135, 95), YELLOW)
        overlay((90, 45, 100, 95), BLEND_BLUE, mode="Multiply")
    return image


def _evidence(image, index):
    """Pixel-only fidelity metric that rejects wrong opacity/blend operators."""
    if image.size != (WIDTH*SCALE, HEIGHT*SCALE):
        return {"matches": 0, "total": len(LANDMARKS[index]), "maxError": 255}
    image = image.convert("RGB")
    errors = [max(abs(a-b) for a, b in zip(
        image.getpixel(_center(x, y)), expected))
        for x, y, expected in LANDMARKS[index]]
    return {
        "matches": sum(error <= 38 for error in errors),
        "total": len(errors),
        "maxError": max(errors),
    }


def _preserves_transparency(evidence):
    return evidence["matches"] == evidence["total"]


class TransparencyFixtureTests(unittest.TestCase):
    def test_two_source_pages_have_real_alpha_blend_and_soft_mask_operators(self):
        reader = PdfReader(BytesIO(_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(page=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)), (WIDTH, HEIGHT))
                self.assertEqual((page.extract_text() or "").strip(), "")
                gs = page["/Resources"]["/ExtGState"]
                settings = gs["/Half" if index == 0 else "/MultiplyHalf"]
                self.assertAlmostEqual(float(settings["/ca"]), 0.5)
                self.assertIn(b" gs ", page.get_contents().get_data())
                if index == 0:
                    self.assertIn(
                        "/SMask", page["/Resources"]["/XObject"]["/Tint"]
                    )
                else:
                    self.assertEqual(settings["/BM"], "/Multiply")
        self.assertNotEqual(reader.pages[0].get_contents().get_data(),
                            reader.pages[1].get_contents().get_data())

    def test_independent_metric_rejects_opaque_missing_wrong_blend_and_swaps(self):
        for index in (0, 1):
            with self.subTest(page=index):
                image = _reference(index)
                self.assertTrue(_preserves_transparency(_evidence(image, index)))
                blank = Image.new("RGB", image.size, "white")
                self.assertFalse(_preserves_transparency(_evidence(blank, index)))
                self.assertFalse(_preserves_transparency(_evidence(
                    _reference(1-index), index
                )))
                opaque = image.copy()
                x, y = _center(105 if index == 0 else 112, 98)
                ImageDraw.Draw(opaque).rectangle((x-12, y-12, x+12, y+12),
                    fill=RED if index == 0 else BLEND_BLUE)
                self.assertFalse(_preserves_transparency(_evidence(opaque, index)))
        wrong_blend = _reference(1)
        x, y = _center(112, 98)
        ImageDraw.Draw(wrong_blend).rectangle((x-12, y-12, x+12, y+12),
            fill=_blend(YELLOW, BLEND_BLUE))
        self.assertFalse(_preserves_transparency(_evidence(wrong_blend, 1)))
        opaque_mask = _reference(0)
        x, y = _center(68, 23)
        ImageDraw.Draw(opaque_mask).rectangle((x-12, y-12, x+12, y+12),
                                               fill=TINT)
        self.assertFalse(_preserves_transparency(_evidence(opaque_mask, 0)))

    def test_only_optional_converter_is_tested_not_scanner_or_user_settings(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/maximum-sanitized-copy.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("maximum-transparency", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertEqual(workflow.count(
            "python3 test-maximum-transparency.py -v"
        ), 2)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        offer = copies.SanitizedCopyOffer(_pdf(), 2)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)


@unittest.skipUnless(sys.platform == "darwin", "CoreGraphics conversion requires macOS")
class NativeTransparencyFidelityTests(unittest.TestCase):
    def test_real_conversion_preserves_alpha_soft_mask_and_multiply_blending(self):
        source = _pdf()
        offer = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offer, "CoreGraphics must convert both source pages")
        self.assertNotEqual(offer.pdf_bytes, source)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)
        reader = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(page=index):
                self.assertEqual((float(page.mediabox.width),
                                  float(page.mediabox.height)), (WIDTH, HEIGHT))
                self.assertEqual((page.extract_text() or "").strip(), "")
                images = list(page.images)
                self.assertEqual(len(images), 1)
                with Image.open(BytesIO(images[0].data)) as rendered:
                    self.assertEqual(rendered.size, (WIDTH*SCALE, HEIGHT*SCALE))
                    evidence = _evidence(rendered, index)
                    self.assertTrue(_preserves_transparency(evidence),
                                    f"Converted page {index+1} lost transparency: {evidence}")
                    self.assertFalse(_preserves_transparency(
                        _evidence(rendered, 1-index)), "Source page order changed")


if __name__ == "__main__":
    unittest.main()
