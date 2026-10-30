#!/usr/bin/env python3
"""opener-0453: extract declared PDF metadata without trusting its contents."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ByteStringObject, DecodedStreamObject, DictionaryObject, NameObject,
    NumberObject, TextStringObject,
)

from pdf_declared_metadata import (
    MAX_METADATA_TEXT, MAX_XMP_BYTES, PDFDeclaredMetadata,
    PDFDeclaredMetadataError, extract_pdf_declared_metadata,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent
_ERROR = "PDF declared metadata could not be fully extracted; opening was stopped."


def document(writer):
    out = BytesIO()
    writer.write(out)
    return out.getvalue()


def pdf_writer():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    return writer


def xmp_xml(*, title="XMP private title", creator="XMP author"):
    return ((
        '<?xpacket begin=""?>'
        '<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"'
        ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
        ' xmlns:pdf="http://ns.adobe.com/pdf/1.3/"'
        ' xmlns:xmp="http://ns.adobe.com/xap/1.0/">'
        '<rdf:Description pdf:Producer="Producer 1"'
        ' xmp:CreateDate="2026-10-29T08:00:00Z">'
        '<dc:title><rdf:Alt><rdf:li xml:lang="x-default">'
        + title + '</rdf:li></rdf:Alt></dc:title>'
        '<dc:creator><rdf:Seq><rdf:li>' + creator + '</rdf:li></rdf:Seq></dc:creator>'
        '</rdf:Description></rdf:RDF></x:xmpmeta>'
        '<?xpacket end="w"?>'
    )).encode("utf-8")


def with_xmp(writer, data, *, compressed=False, type_value="/Metadata",
             subtype_value="/XML"):
    stream = DecodedStreamObject()
    stream.set_data(data)
    stream[NameObject("/Type")] = NameObject(type_value)
    stream[NameObject("/Subtype")] = NameObject(subtype_value)
    if compressed:
        stream = stream.flate_encode()
    writer._root_object[NameObject("/Metadata")] = writer._add_object(stream)
    return writer


class PDFDeclaredMetadataTests(unittest.TestCase):
    def assert_rejected(self, contents):
        with self.assertRaises(PDFDeclaredMetadataError) as failure:
            extract_pdf_declared_metadata(contents)
        self.assertEqual(str(failure.exception), _ERROR)
        self.assertNotIn("PRIVATE", str(failure.exception))

    def test_valid_reference_pdfs_have_no_declared_metadata(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(sample=sample.identifier):
                result = extract_pdf_declared_metadata(sample.content)
                self.assertEqual(result, PDFDeclaredMetadata((), (), False))
                self.assertEqual(result.to_dict(), {
                    "schemaVersion": 1, "info": {}, "xmp": {},
                    "hasXMP": False, "authorizesOpen": False,
                })

    def test_info_dictionary_extracts_declared_standard_fields(self):
        writer = pdf_writer()
        writer.add_metadata({
            "/Title": "PRIVATE: A story",
            "/Author": "Example Author",
            "/Subject": "Subject",
            "/Keywords": "one, two",
            "/Creator": "Creator app",
            "/Producer": "Producer app",
            "/CreationDate": "D:20261029080000Z",
            "/ModDate": "D:20261030080000Z",
            "/Unrecognized": "not part of the supported contract",
        })
        writer._info.get_object()[NameObject("/Trapped")] = NameObject("/False")
        result = extract_pdf_declared_metadata(document(writer))
        info = dict(result.info_fields)
        self.assertEqual(info, {
            "title": "PRIVATE: A story", "author": "Example Author",
            "subject": "Subject", "keywords": "one, two",
            "creator": "Creator app", "producer": "Producer app",
            "creationDate": "D:20261029080000Z",
            "modificationDate": "D:20261030080000Z",
            "trapped": "false",
        })
        self.assertNotIn("Unrecognized", str(info))
        self.assertFalse(result.has_xmp_stream)
        self.assertNotIn("PRIVATE", repr(result))
        self.assertFalse(result.authorizes_open)
        detached = result.to_dict()
        detached["info"]["title"] = "modified"
        detached["authorizesOpen"] = True
        self.assertEqual(dict(result.info_fields)["title"], "PRIVATE: A story")
        self.assertFalse(result.to_dict()["authorizesOpen"])
        with self.assertRaises(FrozenInstanceError):
            result.has_xmp_stream = True

    def test_xmp_rdf_declared_metadata_is_extracted_independently(self):
        writer = pdf_writer()
        writer.add_metadata({"/Title": "Info value", "/Author": "Info author"})
        with_xmp(writer, xmp_xml(), compressed=False)
        result = extract_pdf_declared_metadata(document(writer))
        self.assertTrue(result.has_xmp_stream)
        self.assertEqual(dict(result.xmp_fields), {
            "title": "XMP private title",
            "author": "XMP author",
            "producer": "Producer 1",
            "creationDate": "2026-10-29T08:00:00Z",
        })
        self.assertEqual(dict(result.info_fields)["title"], "Info value")
        self.assertEqual(result.to_dict()["xmp"]["author"], "XMP author")
        self.assertNotIn("XMP private title", repr(result))
        self.assertNotIn("Info value", repr(result))
        self.assertIs(result.to_dict()["authorizesOpen"], False)
        self.assertEqual(json.loads(json.dumps(result.to_dict())), result.to_dict())

    def test_flate_xmp_metadata_is_supported(self):
        writer = pdf_writer()
        with_xmp(writer, xmp_xml(title="Compressed title"), compressed=True)
        result = extract_pdf_declared_metadata(document(writer))
        self.assertEqual(dict(result.xmp_fields)["title"], "Compressed title")

    def test_xmp_without_selected_fields_still_records_presence(self):
        writer = pdf_writer()
        data = (
            b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            b'<rdf:Description /></rdf:RDF>'
        )
        with_xmp(writer, data)
        result = extract_pdf_declared_metadata(document(writer))
        self.assertTrue(result.has_xmp_stream)
        self.assertEqual(result.xmp_fields, ())

    def test_non_metadata_pdf_values_fail_closed_instead_of_guessing(self):
        writer = pdf_writer()
        writer._root_object[NameObject("/Metadata")] = NumberObject(123)
        self.assert_rejected(document(writer))

        writer = pdf_writer()
        with_xmp(writer, xmp_xml(), subtype_value="/NotXML")
        self.assert_rejected(document(writer))

        writer = pdf_writer()
        writer._info.get_object()[NameObject("/Title")] = NumberObject(42)
        self.assert_rejected(document(writer))

        writer = pdf_writer()
        writer._info.get_object()[NameObject("/Title")] = ByteStringObject(b"\xfe\xff\x00")
        self.assert_rejected(document(writer))

        writer = pdf_writer()
        writer._info.get_object()[NameObject("/Trapped")] = NameObject("/Maybe")
        self.assert_rejected(document(writer))

    def test_xmp_entities_invalid_and_oversized_payloads_fail_closed(self):
        invalid = (
            b'<!DOCTYPE rdf:RDF [<!ENTITY private "SECRET">]>'
            b'<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">&private;</rdf:RDF>',
            b'<rdf:RDF', b'\xff\xff',
            b'<html><head></head></html>',
            b' ' * (MAX_XMP_BYTES + 1),
            xmp_xml(title="A" * (MAX_METADATA_TEXT + 1)),
            xmp_xml(title="\x01"),
        )
        for data in invalid:
            with self.subTest(size=len(data), prefix=repr(data[:10])):
                writer = pdf_writer()
                with_xmp(writer, data)
                self.assert_rejected(document(writer))

    def test_oversized_and_control_characters_in_info_fail_closed(self):
        for value in ("X" * (MAX_METADATA_TEXT + 1), "PRIVATE\x00VALUE",
                      "PRIVATE\nVALUE"):
            with self.subTest(length=len(value)):
                writer = pdf_writer()
                writer.add_metadata({"/Title": value})
                self.assert_rejected(document(writer))

    def test_encrypted_corrupt_and_unavailable_parser_fail_closed(self):
        writer = pdf_writer()
        writer.encrypt("sample-fixture-password")
        inputs = (
            document(writer), None, b"not a PDF", b"%PDF-1.4\n%%EOF\n",
            b"x" * (16 * 1024 * 1024 + 1),
        )
        for value in inputs:
            with self.subTest(kind=type(value).__name__):
                self.assert_rejected(value)

        original_import = builtins.__import__

        def unavailable(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("/private/secret-parser-path")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=unavailable):
            self.assert_rejected(REFERENCE_PDFS[0].content)

    def test_result_validation_and_scanner_isolation(self):
        for invalid in (
            (("title", ""),), (("arbitrary", "private"),),
            (("title", "X" * (MAX_METADATA_TEXT + 1)),),
            (("title", "one"), ("title", "two")),
            (("title", "x"), ("author", "y")),
        ):
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    PDFDeclaredMetadata(invalid, (), False)

        with self.assertRaises(TypeError):
            PDFDeclaredMetadata((), (), False, True)
        source = (ROOT / "pdf_declared_metadata.py").read_text()
        scanner = (ROOT / "scan-and-open.py").read_text()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        docs = (ROOT / "docs/pdf/declared-metadata.md").read_text()
        self.assertNotIn("pdf_declared_metadata", scanner)
        self.assertIn("python3 test-pdf-declared-metadata.py -v", ci)
        self.assertIn("/Info", docs)
        self.assertIn("/Metadata", docs)
        for forbidden in ("subprocess.", "launch_clean_file(",
                          "remove_quarantine(", "write_text(",
                          "UserDefaults", "os.environ", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
