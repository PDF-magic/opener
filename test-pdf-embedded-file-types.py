#!/usr/bin/env python3
"""opener-0455: classify PDF embedded files by actual bytes, not their names."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import json
import unittest

from pypdf import PdfWriter
from pypdf.generic import ArrayObject, NameObject, NumberObject, TextStringObject

from pdf_embedded_file_types import (
    MAX_ATTACHMENT_BYTES, PDFEmbeddedFileTypeError, PDFEmbeddedFileTypes,
    inspect_pdf_embedded_file_types,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent
_FAILURE = "Embedded PDF file types could not be fully inspected; opening was stopped."


def pdf_with(*attachments):
    writer = PdfWriter()
    writer.add_blank_page(width=320, height=320)
    for name, payload in attachments:
        writer.add_attachment(name, payload)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def attachment_writer(name="sample.png", payload=b"plain text"):
    writer = PdfWriter()
    writer.add_blank_page(width=320, height=320)
    writer.add_attachment(name, payload)
    specification = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()
    stream = specification["/EF"]["/F"].get_object()
    return writer, specification, stream


def serialize(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class PDFEmbeddedFileTypeTests(unittest.TestCase):
    def assert_blocked(self, contents):
        with self.assertRaises(PDFEmbeddedFileTypeError) as caught:
            inspect_pdf_embedded_file_types(contents)
        self.assertEqual(str(caught.exception), _FAILURE)
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_no_attachments_and_reference_documents_are_non_authorizing(self):
        self.assertEqual(inspect_pdf_embedded_file_types(pdf_with()),
                         PDFEmbeddedFileTypes(0, 0, (), 0, 0, 0, 0))
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                result = inspect_pdf_embedded_file_types(sample.content)
                self.assertEqual(result.attachment_count, 0)
                self.assertFalse(result.authorizes_open)

    def test_actual_magic_bytes_take_precedence_over_filename(self):
        pdf_data = b"%PDF-1.4\nnot a valid standalone embedded PDF"
        png_data = b"\x89PNG\r\n\x1a\nimage bytes"
        zip_data = b"PK\x03\x04archive data"
        payload = pdf_with(("picture.png", pdf_data), ("report.txt", png_data),
                           ("archive.zip", zip_data))
        result = inspect_pdf_embedded_file_types(payload)
        self.assertEqual(result.attachment_count, 3)
        self.assertEqual(result.inspected_bytes, len(pdf_data)+len(png_data)+len(zip_data))
        self.assertEqual(result.detected_kinds, ("pdf", "png", "zip"))
        self.assertEqual(result.extension_mismatch_count, 2)
        self.assertEqual(result.declaration_mismatch_count, 0)
        self.assertEqual(result.unknown_count, 0)
        self.assertFalse(result.authorizes_open)
        self.assertEqual(result.to_dict()["detectedKinds"], ["pdf", "png", "zip"])
        self.assertNotIn("picture.png", repr(result))
        self.assertNotIn("picture.png", json.dumps(result.to_dict()))

    def test_declared_mime_and_extension_mismatches_are_distinct(self):
        writer, spec, stream = attachment_writer("photo.png", b"regular text content")
        stream[NameObject("/Subtype")] = NameObject("/image#2Fpng")
        evidence = inspect_pdf_embedded_file_types(serialize(writer))
        self.assertEqual(evidence.detected_kinds, ("text",))
        self.assertEqual(evidence.declaration_mismatch_count, 1)
        self.assertEqual(evidence.extension_mismatch_count, 1)
        self.assertEqual(evidence.executable_count, 0)

        writer, spec, stream = attachment_writer("report.txt", b"regular text content")
        stream[NameObject("/Subtype")] = NameObject("/text#2Fplain")
        matched = inspect_pdf_embedded_file_types(serialize(writer))
        self.assertEqual(matched.declaration_mismatch_count, 0)
        self.assertEqual(matched.extension_mismatch_count, 0)

    def test_recognizes_common_document_and_executable_signatures(self):
        fixtures = (
            ("image.jpg", b"\xff\xd8\xff\xe0x", "jpeg"),
            ("animation.gif", b"GIF89a123", "gif"),
            ("archive.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1a", "ole"),
            ("program.exe", b"MZ\x00\x00executable", "pe_or_dos"),
            ("program.bin", b"\x7fELF\x02\x01", "elf"),
            ("program.wasm", b"\x00asm\x01\x00\x00\x00", "wasm"),
            ("script.sh", b"#!/bin/sh\necho harmless\n", "script"),
            ("web.html", b"<!DOCTYPE html><html></html>", "html"),
            ("record.xml", b'<?xml version="1.0"?><root/>', "xml"),
            ("doc.rtf", b"{\\rtf1 sample}", "rtf"),
            ("unicode.txt", "hello ü".encode("utf-8"), "text"),
            ("unknown.bin", b"\x00\xff\x88\x80", "unknown_binary"),
        )
        for filename, payload, expected in fixtures:
            with self.subTest(filename=filename):
                result = inspect_pdf_embedded_file_types(pdf_with((filename, payload)))
                self.assertEqual(result.detected_kinds, (expected,))
                self.assertEqual(result.unknown_count, int(expected == "unknown_binary"))
                self.assertEqual(result.executable_count, int(expected in {
                    "pe_or_dos", "elf", "wasm", "script", "mach_o", "java_or_fat_binary"
                }))

    def test_name_tree_associated_file_and_annotation_attachments(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_attachment("private.png", b"\x89PNG\r\n\x1a\nbytes")
        spec = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1]
        del writer._root_object[NameObject("/Names")]
        writer._root_object[NameObject("/AF")] = ArrayObject([spec])
        result = inspect_pdf_embedded_file_types(serialize(writer))
        self.assertEqual(result.detected_kinds, ("png",))
        self.assertEqual(result.attachment_count, 1)

        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        writer.add_attachment("private.txt", b"content")
        spec = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1]
        del writer._root_object[NameObject("/Names")]
        from pypdf.generic import DictionaryObject
        annotation = DictionaryObject({
            NameObject("/Subtype"): NameObject("/FileAttachment"),
            NameObject("/FS"): spec,
        })
        writer.pages[0][NameObject("/Annots")] = ArrayObject([writer._add_object(annotation)])
        result = inspect_pdf_embedded_file_types(serialize(writer))
        self.assertEqual(result.detected_kinds, ("text",))
        self.assertEqual(result.attachment_count, 1)

    def test_malformed_and_unsupported_attachment_streams_fail_closed(self):
        writer, spec, stream = attachment_writer()
        stream[NameObject("/Subtype")] = NumberObject(42)
        self.assert_blocked(serialize(writer))

        writer, spec, stream = attachment_writer()
        stream[NameObject("/Filter")] = NameObject("/UnsupportedEncoding")
        self.assert_blocked(serialize(writer))

        writer, spec, stream = attachment_writer()
        spec[NameObject("/UF")] = NumberObject(17)
        self.assert_blocked(serialize(writer))

        writer, spec, stream = attachment_writer()
        spec[NameObject("/UF")] = TextStringObject("PRIVATE" * 150)
        self.assert_blocked(serialize(writer))

    def test_resource_limits_encryption_and_invalid_pdf_fail_closed(self):
        self.assert_blocked(pdf_with(("large.bin", b"a" * (MAX_ATTACHMENT_BYTES+1))))
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("test-only-password")
        self.assert_blocked(serialize(writer))
        for invalid in (None, b"not a PDF", b"%PDF-1.4\n%%EOF\n",
                        bytearray(pdf_with())):
            with self.subTest(kind=type(invalid).__name__):
                self.assert_blocked(invalid)

    def test_invalid_result_cannot_authorize_opening_or_mutate_evidence(self):
        result = PDFEmbeddedFileTypes(1, 11, ("text",), 0, 0, 0, 0)
        detached = result.to_dict()
        detached["detectedKinds"].append("pe_or_dos")
        detached["authorizesOpen"] = True
        self.assertEqual(result.detected_kinds, ("text",))
        self.assertFalse(result.to_dict()["authorizesOpen"])
        with self.assertRaises(FrozenInstanceError):
            result.attachment_count = 99
        for args in (
            (True, 0, (), 0, 0, 0, 0),
            (1, 11, ("made_up",), 0, 0, 0, 0),
            (1, 11, ("png", "pdf"), 0, 0, 0, 0),
            (1, 11, ("text",), 1, 0, 0, 0),
            (1, 11, ("text",), 0, 1, 0, 0),
            (0, 0, ("text",), 0, 0, 0, 0),
        ):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    PDFEmbeddedFileTypes(*args)
        with self.assertRaises(TypeError):
            PDFEmbeddedFileTypes(0, 0, (), 0, 0, 0, 0, True)

    def test_existing_scanner_and_preferences_are_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        source = (ROOT / "pdf_embedded_file_types.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        docs = (ROOT / "docs/pdf-embedded-file-types.md").read_text(encoding="utf-8")
        self.assertNotIn("pdf_embedded_file_types", scanner)
        self.assertIn("python3 test-pdf-embedded-file-types.py -v", workflow)
        self.assertIn("/EmbeddedFiles", docs)
        self.assertIn("ClamAV", docs)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        for forbidden in ("subprocess.run(", "launch_clean_file(",
                          "remove_quarantine(", "write_text(", "UserDefaults",
                          "os.environ", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
