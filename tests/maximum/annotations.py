#!/usr/bin/env python3
"""opener-0524: annotated PDF fidelity and noninteractive Maximum output.

Synthetic fixtures and metric negative controls run on Linux and macOS.
Only macOS invokes the actual CoreGraphics sanitizer (no converter mocks).
"""
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject,
    NumberObject, TextStringObject,
)
import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parents[2]
WIDTH, HEIGHT, SCALE = 240, 180, 2
RED = (214, 35, 42)
BLUE = (28, 78, 216)
GREEN = (32, 161, 70)
ORANGE = (228, 128, 28)
MARKERS = (
    ((40, 120, RED), (175, 50, BLUE)),
    ((60, 55, GREEN), (170, 130, ORANGE)),
)
RECTS = (
    ((20, 90, 85, 140, RED), (135, 30, 220, 75, BLUE)),
    ((20, 30, 105, 80, GREEN), (135, 105, 215, 155, ORANGE)),
)
EXPECTED_KINDS = (("/Link", "/Highlight"), ("/Text", "/FreeText"))


def _numbers(values):
    return ArrayObject([NumberObject(value) for value in values])


def _appearance(writer, color):
    """A real annotation /AP Form XObject, not part of page /Contents."""
    stream = DecodedStreamObject()
    stream.set_data(b"q 1 0 1 rg 0 0 30 18 re f Q\n")
    stream.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): _numbers((0, 0, 30, 18)),
        NameObject("/Resources"): DictionaryObject(),
    })
    return writer._add_object(stream)


def _add_annotation(writer, page, subtype, bounds, extra):
    annotation = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject(subtype),
        NameObject("/Rect"): _numbers(bounds),
        NameObject("/F"): NumberObject(4),
        NameObject("/Contents"): TextStringObject("PRIVATE-ANNOTATION-CONTENT"),
    })
    annotation.update(extra)
    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    page[NameObject("/Annots")].append(writer._add_object(annotation))


def _pdf():
    writer = PdfWriter()
    for index, boxes in enumerate(RECTS):
        page = writer.add_blank_page(width=WIDTH, height=HEIGHT)
        operators = []
        for x0, y0, x1, y1, color in boxes:
            rgb = " ".join(f"{value / 255:.6f}" for value in color)
            operators.append(
                f"q {rgb} rg {x0} {y0} {x1-x0} {y1-y0} re f Q\n"
            )
        operators.append("q 0 0 0 RG 1 w 24 13 m 212 13 l S Q\n")
        content = DecodedStreamObject()
        content.set_data("".join(operators).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(content)

        if index == 0:
            _add_annotation(writer, page, "/Link", (94, 85, 129, 107), {
                NameObject("/Border"): _numbers((0, 0, 0)),
                NameObject("/A"): DictionaryObject({
                    NameObject("/S"): NameObject("/URI"),
                    NameObject("/URI"): TextStringObject(
                        "https://private.example.test/do-not-contact"
                    ),
                }),
            })
            _add_annotation(writer, page, "/Highlight", (90, 141, 132, 165), {
                NameObject("/C"): ArrayObject([
                    NumberObject(1), NumberObject(1), NumberObject(0),
                ]),
                NameObject("/QuadPoints"): _numbers(
                    (90, 165, 132, 165, 90, 141, 132, 141)
                ),
                NameObject("/AP"): DictionaryObject({
                    NameObject("/N"): _appearance(writer, "magenta"),
                }),
            })
        else:
            _add_annotation(writer, page, "/Text", (112, 91, 129, 108), {
                NameObject("/Name"): NameObject("/Comment"),
                NameObject("/T"): TextStringObject("PRIVATE-NOTE-AUTHOR"),
            })
            _add_annotation(writer, page, "/FreeText", (108, 26, 132, 57), {
                NameObject("/DA"): TextStringObject("/Helv 9 Tf 0 g"),
                NameObject("/AP"): DictionaryObject({
                    NameObject("/N"): _appearance(writer, "magenta"),
                }),
            })

    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _image_point(x, y):
    return round(x * SCALE), round((HEIGHT - y) * SCALE)


def _reference_image(index):
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "white")
    draw = ImageDraw.Draw(image)
    for x0, y0, x1, y1, color in RECTS[index]:
        draw.rectangle(
            (x0 * SCALE, (HEIGHT - y1) * SCALE,
             x1 * SCALE - 1, (HEIGHT - y0) * SCALE - 1),
            fill=color,
        )
    draw.line((_image_point(24, 13), _image_point(212, 13)),
              fill="black", width=2)
    return image


def _visual_evidence(image, index):
    """Independent fixed-color and page-order checks, not OCR or PDF semantics."""
    if image.size != (WIDTH * SCALE, HEIGHT * SCALE):
        return False
    image = image.convert("RGB")
    for x, y, expected in MARKERS[index]:
        observed = image.getpixel(_image_point(x, y))
        if max(abs(observed[k] - expected[k]) for k in range(3)) > 48:
            return False
    for x, y in ((8, 15), (226, 164), (121, 72)):
        if min(image.getpixel(_image_point(x, y))) < 225:
            return False
    # Two independent points on the fine horizontal page rule.
    for x in (55, 182):
        if max(image.getpixel(_image_point(x, 13))) > 135:
            return False
    return True


class AnnotatedSourceFixtureTests(unittest.TestCase):
    def test_source_has_real_annotations_with_separate_page_content(self):
        reader = PdfReader(BytesIO(_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        for index, page in enumerate(reader.pages):
            with self.subTest(page=index):
                self.assertEqual(
                    (float(page.mediabox.width), float(page.mediabox.height)),
                    (WIDTH, HEIGHT),
                )
                annots = page["/Annots"]
                self.assertEqual(len(annots), 2)
                self.assertEqual(
                    tuple(item.get_object()["/Subtype"] for item in annots),
                    EXPECTED_KINDS[index],
                )
                self.assertEqual(len(page.images), 0)
                self.assertIn(b" re f Q", page.get_contents().get_data())
                for item in annots:
                    self.assertIn("PRIVATE-ANNOTATION-CONTENT",
                                  item.get_object()["/Contents"])
        page1 = reader.pages[0]
        link = page1["/Annots"][0].get_object()
        self.assertEqual(link["/A"]["/S"], "/URI")
        self.assertIn("private.example.test", link["/A"]["/URI"])
        highlight = page1["/Annots"][1].get_object()
        self.assertEqual(highlight["/AP"]["/N"].get_object()["/Subtype"], "/Form")
        free_text = reader.pages[1]["/Annots"][1].get_object()
        self.assertEqual(free_text["/AP"]["/N"].get_object()["/Subtype"], "/Form")

    def test_visual_metric_detects_missing_page_content_and_order_changes(self):
        for index in (0, 1):
            with self.subTest(page=index):
                expected = _reference_image(index)
                self.assertTrue(_visual_evidence(expected, index))
                self.assertFalse(_visual_evidence(
                    Image.new("RGB", expected.size, "white"), index
                ))
                self.assertFalse(_visual_evidence(_reference_image(1-index), index))
                erased = expected.copy()
                ImageDraw.Draw(erased).rectangle(
                    (20 * SCALE, 20 * SCALE,
                     225 * SCALE, 155 * SCALE), fill="white"
                )
                self.assertFalse(_visual_evidence(erased, index))
                shifted = Image.new("RGB", expected.size, "white")
                shifted.paste(expected.crop((110, 0, expected.width, expected.height)),
                              (0, 0))
                self.assertFalse(_visual_evidence(shifted, index))

    def test_annotation_policy_and_scanner_remain_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/consolidated-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("maximum-annotations", scanner)
        self.assertIn("python3 tests/maximum/annotations.py -v", workflow)
        self.assertFalse(copies.SanitizedCopyOffer(_pdf(), 2).permits_open)
        self.assertTrue(copies.SanitizedCopyOffer(_pdf(), 2).needs_separate_scan)
        self.assertIn("other interactive features are not preserved", copies.OFFER_EXPLANATION)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


@unittest.skipUnless(sys.platform == "darwin", "Native CoreGraphics requires macOS")
class NativeAnnotationFidelityTests(unittest.TestCase):
    def test_real_conversion_keeps_page_art_and_drops_interactive_annotations(self):
        original = _pdf()
        offer = copies.offer_sanitized_pdf_copy(original)
        self.assertIsNotNone(offer, "Supported annotations need a visual-only offer")
        self.assertNotEqual(offer.pdf_bytes, original)
        self.assertFalse(offer.permits_open)
        self.assertTrue(offer.needs_separate_scan)
        self.assertTrue(offer.rasterized)
        generated = PdfReader(BytesIO(offer.pdf_bytes), strict=True)
        self.assertEqual(len(generated.pages), 2)
        self.assertNotIn("PRIVATE-ANNOTATION-CONTENT", repr(generated.trailer))
        self.assertNotIn("private.example.test", repr(generated.trailer))
        self.assertNotIn("/AcroForm", generated.trailer["/Root"])
        self.assertNotIn("/Names", generated.trailer["/Root"])
        for index, page in enumerate(generated.pages):
            with self.subTest(page=index):
                self.assertEqual(
                    (float(page.mediabox.width), float(page.mediabox.height)),
                    (WIDTH, HEIGHT),
                )
                self.assertNotIn("/Annots", page)
                self.assertNotIn("/AA", page)
                self.assertNotIn("/A", page)
                self.assertEqual((page.extract_text() or "").strip(), "")
                images = list(page.images)
                self.assertEqual(len(images), 1)
                with Image.open(BytesIO(images[0].data)) as picture:
                    self.assertTrue(
                        _visual_evidence(picture, index),
                        f"Converted annotated page {index+1} lost base artwork",
                    )


if __name__ == "__main__":
    unittest.main()
