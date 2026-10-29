#!/usr/bin/env python3
"""opener-0315: no PDF active features cross the rasterized-output boundary."""
from io import BytesIO
from pathlib import Path
import unittest
import zlib

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, NumberObject, StreamObject, TextStringObject

import maximum_active_content_removal as removal


def executable_payload():
    """PE-like attachment payload that must not survive visual-only rebuilding."""
    header = bytearray(128)
    header[:2] = b"MZ"
    header[60:64] = (64).to_bytes(4, "little")
    header[64:68] = b"PE" + bytes(2)
    return bytes(header) + b"PRIVATE-EXECUTABLE-PAYLOAD"


def image_pdf(*, pages=1, actions=False, form_actions=False, extra_image=False, size=(24, 30)):
    writer = PdfWriter()
    for number in range(pages):
        page = writer.add_blank_page(width=72 + number, height=90 + number)
        pixels = Image.new("RGB", size, (12 + number, 140, 235)).tobytes()
        raster = StreamObject()
        raster._data = zlib.compress(pixels)
        raster.update({
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(size[0]),
            NameObject("/Height"): NumberObject(size[1]),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/Filter"): NameObject("/FlateDecode"),
        })
        ref = writer._add_object(raster)
        images = DictionaryObject({NameObject("/Im0"): ref})
        if extra_image:
            images[NameObject("/Im1")] = ref
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/XObject"): images,
        })
        content = StreamObject()
        content._data = b"q 72 0 0 90 0 0 cm /Im0 Do Q\n"
        page[NameObject("/Contents")] = writer._add_object(content)
        if actions:
            page[NameObject("/AA")] = DictionaryObject({
                NameObject("/O"): DictionaryObject({
                    NameObject("/S"): NameObject("/JavaScript"),
                }),
            })
            page[NameObject("/Annots")] = writer._add_object(DictionaryObject({
                NameObject("/S"): NameObject("/Launch"),
            }))
    if form_actions:
        # A real AcroForm widget with direct and additional form actions.
        # All targets and field names are intentionally private markers.
        field_name = "PRIVATE-FORM-FIELD"
        submit_action = writer._add_object(DictionaryObject({
            NameObject("/S"): NameObject("/SubmitForm"),
            NameObject("/F"): TextStringObject("https://private.invalid/submit"),
            NameObject("/Fields"): ArrayObject([TextStringObject(field_name)]),
        }))
        reset_action = writer._add_object(DictionaryObject({
            NameObject("/S"): NameObject("/ResetForm"),
            NameObject("/Fields"): ArrayObject([TextStringObject(field_name)]),
        }))
        import_action = writer._add_object(DictionaryObject({
            NameObject("/S"): NameObject("/ImportData"),
            NameObject("/F"): TextStringObject("private-form.fdf"),
        }))
        widget = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Widget"),
            NameObject("/FT"): NameObject("/Btn"),
            NameObject("/T"): TextStringObject(field_name),
            NameObject("/Rect"): ArrayObject([
                NumberObject(0), NumberObject(0), NumberObject(20), NumberObject(20),
            ]),
            NameObject("/A"): submit_action,
            NameObject("/AA"): DictionaryObject({
                NameObject("/U"): reset_action,
                NameObject("/D"): import_action,
            }),
        })
        widget_ref = writer._add_object(widget)
        writer.pages[0][NameObject("/Annots")] = ArrayObject([widget_ref])
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(
            DictionaryObject({
                NameObject("/Fields"): ArrayObject([widget_ref]),
            })
        )

    if actions:
        writer.add_js("app.alert('EVIL-NOT-TO-COPY')")
        writer.add_attachment("private-sensitive.txt", b"SENSITIVE-PAYLOAD-NEVER-COPY")
        writer.add_attachment("dropper.exe", executable_payload())
    stream = BytesIO()
    writer.write(stream)
    return stream.getvalue()


class ActiveRemovalTests(unittest.TestCase):
    def test_rebuilds_fresh_image_only_pages_and_excludes_actions(self):
        original = image_pdf(actions=True)
        result = removal.remove_active_pdf_functionality(original, 1)
        self.assertIsInstance(result, bytes)
        self.assertNotEqual(result, original)
        output = PdfReader(BytesIO(result), strict=True)
        self.assertEqual(set(output.trailer["/Root"]), {"/Type", "/Pages"})
        self.assertEqual(len(output.pages), 1)
        self.assertEqual(
            set(output.pages[0]),
            {"/Type", "/Parent", "/Resources", "/MediaBox", "/Contents"},
        )
        self.assertEqual(len(list(output.pages[0].images)), 1)
        for forbidden in ("/AA", "/Annots", "/OpenAction", "/JS", "/AcroForm",
                          "/Names", "/EmbeddedFiles", "/RichMedia"):
            self.assertNotIn(forbidden, output.pages[0])
            self.assertNotIn(forbidden, output.trailer["/Root"])
        self.assertNotIn(b"EVIL-NOT-TO-COPY", result)
        self.assertNotIn(b"SENSITIVE-PAYLOAD-NEVER-COPY", result)
        pixel = Image.open(BytesIO(output.pages[0].images[0].data)).convert("RGB")
        self.assertEqual(pixel.getpixel((0, 0)), (12, 140, 235))

    def test_interactive_form_actions_and_targets_are_stripped(self):
        original = image_pdf(form_actions=True)
        source = PdfReader(BytesIO(original), strict=True)
        root = source.trailer["/Root"]
        self.assertIn("/AcroForm", root)
        form = root["/AcroForm"].get_object()
        fields = form["/Fields"].get_object()
        self.assertEqual(len(fields), 1)
        widget = fields[0].get_object()
        self.assertEqual(str(widget["/A"].get_object()["/S"]), "/SubmitForm")
        additional = widget["/AA"].get_object()
        self.assertEqual(str(additional["/U"].get_object()["/S"]), "/ResetForm")
        self.assertEqual(str(additional["/D"].get_object()["/S"]), "/ImportData")
        self.assertIn(b"PRIVATE-FORM-FIELD", original)
        self.assertIn(b"private-form.fdf", original)
        self.assertIn(b"private.invalid/submit", original)

        result = removal.remove_active_pdf_functionality(original, 1)
        self.assertIsInstance(result, bytes)
        self.assertNotEqual(result, original)
        output = PdfReader(BytesIO(result), strict=True)
        self.assertEqual(set(output.trailer["/Root"]), {"/Type", "/Pages"})
        page = output.pages[0]
        self.assertEqual(set(page), {
            "/Type", "/Parent", "/Resources", "/MediaBox", "/Contents",
        })
        for marker in (
            b"/AcroForm", b"/SubmitForm", b"/ResetForm", b"/ImportData",
            b"/AA", b"/Annots", b"PRIVATE-FORM-FIELD", b"private-form.fdf",
            b"private.invalid/submit",
        ):
            self.assertNotIn(marker, result)

    def test_embedded_executables_and_other_files_are_stripped(self):
        original = image_pdf(actions=True)
        source = PdfReader(BytesIO(original), strict=True)
        names = source.trailer["/Root"]["/Names"]["/EmbeddedFiles"]["/Names"]
        attachments = {}
        for index in range(0, len(names), 2):
            spec = names[index + 1].get_object()
            attachments[str(names[index])] = spec["/EF"]["/F"].get_object().get_data()
        self.assertIn("dropper.exe", attachments)
        self.assertIn(b"PRIVATE-EXECUTABLE-PAYLOAD", attachments["dropper.exe"])
        self.assertIn(b"SENSITIVE-PAYLOAD-NEVER-COPY", attachments["private-sensitive.txt"])

        result = removal.remove_active_pdf_functionality(original, 1)
        self.assertIsInstance(result, bytes)
        self.assertNotIn(b"PRIVATE-EXECUTABLE-PAYLOAD", result)
        self.assertNotIn(b"SENSITIVE-PAYLOAD-NEVER-COPY", result)
        output = PdfReader(BytesIO(result), strict=True)
        self.assertEqual(set(output.trailer["/Root"]), {"/Type", "/Pages"})
        self.assertNotIn("/Names", output.trailer["/Root"])
        self.assertNotIn("/EmbeddedFiles", output.trailer["/Root"])
        self.assertEqual(set(output.pages[0]), {
            "/Type", "/Parent", "/Resources", "/MediaBox", "/Contents",
        })

    def test_preserves_page_count_dimensions_and_distinct_pixels(self):
        result = removal.remove_active_pdf_functionality(
            image_pdf(pages=2, actions=True), 2)
        self.assertIsNotNone(result)
        pages = PdfReader(BytesIO(result), strict=True).pages
        self.assertEqual(len(pages), 2)
        self.assertEqual(float(pages[0].mediabox.width), 72)
        self.assertEqual(float(pages[1].mediabox.width), 73)
        colors = [
            Image.open(BytesIO(page.images[0].data)).convert("RGB").getpixel((0, 0))
            for page in pages
        ]
        self.assertNotEqual(colors[0], colors[1])

    def test_preserves_page_order_dimensions_and_right_angle_rotations(self):
        expected = (
            (72.0, 90.0, 0),
            (73.0, 91.0, 90),
            (74.0, 92.0, 180),
            (75.0, 93.0, 270),
        )
        result = removal.remove_active_pdf_functionality(
            image_pdf(pages=4), 4, expected,
        )
        self.assertIsNotNone(result)
        pages = PdfReader(BytesIO(result), strict=True).pages
        actual = [
            (float(page.mediabox.width), float(page.mediabox.height),
             int(page.get_inherited("/Rotate") or 0) % 360)
            for page in pages
        ]
        self.assertEqual(actual, list(expected))
        colors = [
            Image.open(BytesIO(page.images[0].data)).convert("RGB").getpixel((0, 0))
            for page in pages
        ]
        self.assertEqual(colors, [(12, 140, 235), (13, 140, 235),
                                  (14, 140, 235), (15, 140, 235)])

    def test_geometry_mismatch_and_invalid_rotation_fail_closed(self):
        raster = image_pdf(pages=2)
        self.assertIsNone(removal.remove_active_pdf_functionality(
            raster, 2, ((73.0, 91.0, 0), (72.0, 90.0, 0)),
        ))
        self.assertIsNone(removal.remove_active_pdf_functionality(
            raster, 2, ((72.0, 90.0, 45), (73.0, 91.0, 0)),
        ))
        self.assertIsNone(removal.remove_active_pdf_functionality(
            raster, 2, ((72.0, 90.0, 0),),
        ))

    def test_discarded_source_content_is_replaced_by_fixed_image_drawing(self):
        source = image_pdf(actions=True)
        reader = PdfReader(BytesIO(source))
        self.assertIn("/Names", reader.trailer["/Root"])
        result = removal.remove_active_pdf_functionality(source, 1)
        self.assertIsNotNone(result)
        page = PdfReader(BytesIO(result)).pages[0]
        commands = page["/Contents"].get_object().get_data()
        self.assertEqual(commands.count(b"/Im0 Do"), 1)
        self.assertNotIn(b"/JavaScript", commands)
        self.assertNotIn(b"/Launch", commands)

    def test_rejects_malformed_oversized_or_multi_image_candidates(self):
        source = image_pdf()
        cases = (
            (b"", 1), ("bad", 1), (bytearray(source), 1),
            (b"%PDF-1.7\ninvalid", 1), (source, 0), (source, 2),
            (source, True), (source, 17),
            (b"%PDF-1.7\n" + b"X" * removal.MAX_RASTER_INPUT_BYTES, 1),
            (image_pdf(extra_image=True), 1),
            (image_pdf(size=(2049, 1)), 1),
        )
        for data, pages in cases:
            with self.subTest(type=type(data).__name__, pages=pages):
                self.assertIsNone(removal.remove_active_pdf_functionality(data, pages))

    def test_rejects_encrypted_pdf_and_pages_without_raster_image(self):
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.encrypt("password")
        encrypted = BytesIO()
        writer.write(encrypted)
        self.assertIsNone(removal.remove_active_pdf_functionality(encrypted.getvalue(), 1))
        blank = PdfWriter()
        blank.add_blank_page(width=72, height=72)
        missing = BytesIO()
        blank.write(missing)
        self.assertIsNone(removal.remove_active_pdf_functionality(missing.getvalue(), 1))

    def test_scanner_and_maximum_profile_remain_untouched(self):
        root = Path(__file__).resolve().parent
        scan = (root / "scan-and-open.py").read_text()
        self.assertNotIn("maximum_active_content_removal", scan)
        self.assertIn("if not cached_clean(cache_id):", scan)
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)


if __name__ == "__main__":
    unittest.main()
