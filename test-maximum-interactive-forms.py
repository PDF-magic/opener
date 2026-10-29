#!/usr/bin/env python3
"""opener-0525: real interactive forms and lossy Maximum PDF fidelity.

Linux and macOS validate deterministic AcroForm fixtures and pixel negative
controls. Only macOS invokes the real CoreGraphics converter. No mock
sanitizer, opening, or scan-policy changes.
"""
from io import BytesIO
from pathlib import Path
import sys
import unittest

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, BooleanObject, DecodedStreamObject, DictionaryObject,
    NameObject, NumberObject, TextStringObject,
)

import maximum_sanitized_copy as copies

ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT, SCALE = 300, 220, 2
RED = (212, 38, 38)
BLUE = (37, 66, 209)
GREEN = (38, 166, 77)
ORANGE = (226, 129, 28)
BOXES = (
    ((20, 146, 90, 195, RED), (216, 26, 282, 70, BLUE)),
    ((20, 25, 91, 69, GREEN), (213, 147, 283, 193, ORANGE)),
)
MARKERS = (
    ((50, 168, RED), (247, 49, BLUE)),
    ((50, 46, GREEN), (247, 168, ORANGE)),
)
EXPECTED_FIELDS = (
    (("PRIVATE-TEXT-FIELD", "/Tx", "PRIVATE-entered-name"),
     ("PRIVATE-CHECK-BOX", "/Btn", "/Yes")),
    (("PRIVATE-CHOICE-FIELD", "/Ch", "PRIVATE-selected-choice"),),
)


def _numbers(items):
    return ArrayObject([NumberObject(value) for value in items])


def _appearance(writer, *, checked=False):
    """A true appearance XObject distinct from page /Contents."""
    stream = DecodedStreamObject()
    stream.set_data(
        b"q 0.96 0.96 0.96 rg 0 0 140 23 re f "
        + (b"0 0.5 0 rg 12 6 14 11 re f " if checked else b"")
        + b"0 0 0 RG 1 w 0.5 0.5 139 22 re S Q\n"
    )
    stream.update({
        NameObject("/Type"): NameObject("/XObject"),
        NameObject("/Subtype"): NameObject("/Form"),
        NameObject("/BBox"): _numbers((0, 0, 140, 23)),
        NameObject("/Resources"): DictionaryObject(),
    })
    return writer._add_object(stream)


def _field(writer, page, *, title, kind, value, bounds):
    field = DictionaryObject({
        NameObject("/FT"): NameObject(kind),
        NameObject("/T"): TextStringObject(title),
        NameObject("/Ff"): NumberObject(0),
        NameObject("/V"): (
            NameObject(value) if kind == "/Btn" else TextStringObject(value)
        ),
    })
    if kind == "/Ch":
        field[NameObject("/Opt")] = ArrayObject([
            TextStringObject("PRIVATE-selected-choice"),
            TextStringObject("PUBLIC-OTHER"),
        ])
    field_ref = writer._add_object(field)
    normal = _appearance(writer, checked=(kind == "/Btn"))
    widget = DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/Widget"),
        NameObject("/Rect"): _numbers(bounds),
        NameObject("/F"): NumberObject(4),
        NameObject("/Parent"): field_ref,
        NameObject("/AP"): DictionaryObject({
            NameObject("/N"): (
                DictionaryObject({
                    NameObject("/Off"): _appearance(writer),
                    NameObject("/Yes"): normal,
                }) if kind == "/Btn" else normal
            ),
        }),
    })
    if kind == "/Btn":
        widget[NameObject("/AS")] = NameObject("/Yes")
    ref = writer._add_object(widget)
    field[NameObject("/Kids")] = ArrayObject([ref])
    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    page[NameObject("/Annots")].append(ref)
    return field_ref


def _source_pdf():
    writer = PdfWriter()
    all_fields = []
    for index, boxes in enumerate(BOXES):
        page = writer.add_blank_page(width=WIDTH, height=HEIGHT)
        commands = []
        for x0, y0, x1, y1, color in boxes:
            rgb = " ".join(f"{component / 255:.6f}" for component in color)
            commands.append(
                f"q {rgb} rg {x0} {y0} {x1-x0} {y1-y0} re f Q\n".encode("ascii")
            )
        # Static artwork is independent of the editable widget appearances.
        commands.append(b"q 0 0 0 RG 1 w 20 13 m 280 13 l S Q\n")
        content = DecodedStreamObject()
        content.set_data(b"".join(commands))
        page[NameObject("/Contents")] = writer._add_object(content)
        if index == 0:
            all_fields.append(_field(
                writer, page, title="PRIVATE-TEXT-FIELD", kind="/Tx",
                value="PRIVATE-entered-name", bounds=(98, 151, 201, 176),
            ))
            all_fields.append(_field(
                writer, page, title="PRIVATE-CHECK-BOX", kind="/Btn",
                value="/Yes", bounds=(101, 92, 125, 114),
            ))
        else:
            all_fields.append(_field(
                writer, page, title="PRIVATE-CHOICE-FIELD", kind="/Ch",
                value="PRIVATE-selected-choice", bounds=(97, 92, 211, 118),
            ))
    writer._root_object[NameObject("/AcroForm")] = writer._add_object(
        DictionaryObject({
            NameObject("/Fields"): ArrayObject(all_fields),
            NameObject("/NeedAppearances"): BooleanObject(False),
            NameObject("/DA"): TextStringObject("/Helv 10 Tf 0 g"),
        })
    )
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _point(x, y):
    return round(x * SCALE), round((HEIGHT - y) * SCALE)


def _reference_image(index, *, include_rule=True):
    image = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), "white")
    draw = ImageDraw.Draw(image)
    for x0, y0, x1, y1, color in BOXES[index]:
        draw.rectangle(
            (x0 * SCALE, (HEIGHT - y1) * SCALE,
             x1 * SCALE - 1, (HEIGHT - y0) * SCALE - 1),
            fill=color,
        )
    if include_rule:
        draw.line((_point(20, 13), _point(280, 13)), fill="black", width=2)
    return image


def _retains_underlay(image, index):
    """Conservative artwork/order measurement independent of widget values."""
    if image.size != (WIDTH * SCALE, HEIGHT * SCALE):
        return False
    rgb = image.convert("RGB")
    for x, y, expected in MARKERS[index]:
        actual = rgb.getpixel(_point(x, y))
        if max(abs(a-b) for a, b in zip(actual, expected)) > 48:
            return False
    for x, y in ((8, 15), (290, 207), (150, 40)):
        if min(rgb.getpixel(_point(x, y))) < 215:
            return False
    for x in (30, 268):
        if max(rgb.getpixel(_point(x, 13))) > 145:
            return False
    return True


class InteractiveFormFixtureTests(unittest.TestCase):
    def test_source_contains_real_acroform_fields_and_widget_appearances(self):
        reader = PdfReader(BytesIO(_source_pdf()), strict=True)
        self.assertEqual(len(reader.pages), 2)
        form = reader.trailer["/Root"]["/AcroForm"].get_object()
        self.assertFalse(form["/NeedAppearances"])
        fields = [ref.get_object() for ref in form["/Fields"]]
        self.assertEqual(len(fields), 3)
        self.assertEqual(len(reader.get_fields()), 3)
        kinds = []
        for field in fields:
            kinds.append((str(field["/T"]), str(field["/FT"]),
                          str(field["/V"])))
            self.assertEqual(len(field["/Kids"]), 1)
            widget = field["/Kids"][0].get_object()
            self.assertEqual(widget["/Subtype"], "/Widget")
            self.assertEqual(widget["/Parent"].get_object(), field)
            self.assertIn("/AP", widget)
            self.assertIn("/N", widget["/AP"])
        self.assertEqual(tuple(kinds), EXPECTED_FIELDS[0] + EXPECTED_FIELDS[1])
        self.assertEqual(len(reader.pages[0]["/Annots"]), 2)
        self.assertEqual(len(reader.pages[1]["/Annots"]), 1)
        choice = fields[2]
        self.assertEqual(len(choice["/Opt"]), 2)
        checkbox = fields[1]["/Kids"][0].get_object()
        self.assertEqual(checkbox["/AS"], "/Yes")
        self.assertIn("/Off", checkbox["/AP"]["/N"])
        self.assertIn("/Yes", checkbox["/AP"]["/N"])
        for index, page in enumerate(reader.pages):
            with self.subTest(page=index):
                self.assertEqual(
                    (float(page.mediabox.width), float(page.mediabox.height)),
                    (WIDTH, HEIGHT),
                )
                self.assertEqual(len(page.images), 0)
                self.assertIn(b" re f Q", page.get_contents().get_data())

    def test_visual_metrics_reject_blank_missing_shifted_or_reordered_pages(self):
        for index in range(2):
            with self.subTest(page=index):
                expected = _reference_image(index)
                self.assertTrue(_retains_underlay(expected, index))
                self.assertFalse(_retains_underlay(
                    Image.new("RGB", expected.size, "white"), index
                ))
                self.assertFalse(_retains_underlay(_reference_image(1-index), index))
                self.assertFalse(_retains_underlay(
                    _reference_image(index, include_rule=False), index
                ))
                shifted = Image.new("RGB", expected.size, "white")
                shifted.paste(expected.crop((90, 0, expected.width, expected.height)),
                              (0, 0))
                self.assertFalse(_retains_underlay(shifted, index))

    def test_existing_scanner_sanitizer_and_user_preferences_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/maximum-sanitized-copy.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("test-maximum-interactive-forms.py", scanner)
        self.assertIn("python3 test-maximum-interactive-forms.py -v", workflow)
        self.assertIn("forms", copies.OFFER_EXPLANATION)
        offer = copies.SanitizedCopyOffer(_source_pdf(), 2)
        self.assertTrue(offer.rasterized)
        self.assertTrue(offer.needs_separate_scan)
        self.assertFalse(offer.permits_open)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


@unittest.skipUnless(sys.platform == "darwin", "Native CoreGraphics requires macOS")
class NativeInteractiveFormFidelityTests(unittest.TestCase):
    def test_real_converter_keeps_underlay_and_discards_editable_forms(self):
        source = _source_pdf()
        offered = copies.offer_sanitized_pdf_copy(source)
        self.assertIsNotNone(offered, "Supported AcroForm input must yield a raster copy")
        self.assertNotEqual(offered.pdf_bytes, source)
        self.assertTrue(offered.rasterized)
        self.assertTrue(offered.needs_separate_scan)
        self.assertFalse(offered.permits_open)
        result = PdfReader(BytesIO(offered.pdf_bytes), strict=True)
        self.assertEqual(len(result.pages), 2)
        self.assertNotIn("/AcroForm", result.trailer["/Root"])
        self.assertNotIn("/Names", result.trailer["/Root"])
        self.assertNotIn("PRIVATE", repr(result.trailer))
        self.assertEqual(result.get_fields(), {})
        for index, page in enumerate(result.pages):
            with self.subTest(page=index):
                self.assertEqual(
                    (float(page.mediabox.width), float(page.mediabox.height)),
                    (WIDTH, HEIGHT),
                )
                for key in ("/Annots", "/AA", "/A", "/AcroForm", "/Metadata"):
                    self.assertNotIn(key, page)
                self.assertEqual((page.extract_text() or "").strip(), "")
                images = list(page.images)
                self.assertEqual(len(images), 1)
                with Image.open(BytesIO(images[0].data)) as image:
                    self.assertTrue(
                        _retains_underlay(image, index),
                        f"Page {index+1}: sanitized interactive form lost base artwork",
                    )


if __name__ == "__main__":
    unittest.main()
