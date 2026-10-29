#!/usr/bin/env python3
"""opener-0467: identify PDF constructs outside the bounded analyzer."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import builtins
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
    TextStringObject,
)

from pdf_unsupported_feature_inspection import (
    PDFUnsupportedFeatureInspectionError,
    PDFUnsupportedFeatureReport, UnsupportedPDFFeature,
    inspect_pdf_unsupported_features,
)

ROOT = Path(__file__).resolve().parent
ERROR = "PDF feature support could not be fully inspected; opening was stopped."


def serialize(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def blank_writer():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    return writer


def xref_stream_pdf():
    """Create a small xref-stream PDF; detection must precede PdfReader."""
    data = bytearray(b"%PDF-1.5\n")
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    }
    offsets = {}
    for number, body in objects.items():
        offsets[number] = len(data)
        data.extend(f"{number} 0 obj\n".encode("ascii") + body + b"\nendobj\n")
    xref_offset = len(data)
    offsets[4] = xref_offset
    entries = bytearray(b"\x00" + (0).to_bytes(4, "big") + (65535).to_bytes(2, "big"))
    for number in range(1, 5):
        entries.extend(b"\x01" + offsets[number].to_bytes(4, "big") + (0).to_bytes(2, "big"))
    data.extend(
        b"4 0 obj\n<< /Type /XRef /Size 5 /Root 1 0 R /W [1 4 2] /Length 35 >>\nstream\n"
        + entries + b"\nendstream\nendobj\nstartxref\n"
        + str(xref_offset).encode("ascii") + b"\n%%EOF\n"
    )
    return bytes(data)


def feature_writer():
    writer = blank_writer()
    root = writer._root_object
    root[NameObject("/AcroForm")] = DictionaryObject({
        NameObject("/XFA"): TextStringObject("PRIVATE XFA payload marker"),
    })
    root[NameObject("/Names")] = DictionaryObject({
        NameObject("/EmbeddedFiles"): DictionaryObject(),
    })
    root[NameObject("/Collection")] = DictionaryObject()
    root[NameObject("/OCProperties")] = DictionaryObject()
    root[NameObject("/StructTreeRoot")] = DictionaryObject()
    root[NameObject("/Perms")] = DictionaryObject({
        NameObject("/DocMDP"): DictionaryObject({
            NameObject("/Type"): NameObject("/Sig"),
            NameObject("/ByteRange"): ArrayObject([NumberObject(0), NumberObject(1)]),
            NameObject("/Contents"): TextStringObject("PRIVATE signature bytes"),
        }),
    })
    action = writer._add_object(DictionaryObject({
        NameObject("/S"): NameObject("/JavaScript"),
        NameObject("/JS"): TextStringObject("PRIVATE script payload"),
    }))
    root[NameObject("/OpenAction")] = action
    writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/Annot"),
        NameObject("/Subtype"): NameObject("/RichMedia"),
    }))
    writer._add_object(DictionaryObject({
        NameObject("/Type"): NameObject("/3D"),
    }))
    page = writer.pages[0]
    page[NameObject("/Annots")] = ArrayObject()
    stream = DecodedStreamObject()
    stream.set_data(b"PRIVATE page content")
    stream[NameObject("/Filter")] = NameObject("/LZWDecode")
    page[NameObject("/Contents")] = writer._add_object(stream)
    return writer


class UnsupportedPDFFeatureInspectionTests(unittest.TestCase):
    def codes(self, contents):
        return {item.value for item in inspect_pdf_unsupported_features(contents).feature_codes}

    def test_simple_classic_pdf_has_complete_inventory_not_open_authorization(self):
        report = inspect_pdf_unsupported_features(serialize(blank_writer()))
        self.assertEqual(report.feature_codes, ())
        self.assertEqual(report.inspected_object_count, 3)
        self.assertTrue(report.inspection_complete)
        self.assertFalse(report.authorizes_open)
        self.assertFalse(report.has_unsupported_features)
        self.assertEqual(report.to_dict(), {
            "schemaVersion": 1,
            "featureCodes": [],
            "inspectedObjectCount": 3,
            "inspectionComplete": True,
            "authorizesOpen": False,
        })

    def test_identifies_features_and_never_returns_document_strings(self):
        report = inspect_pdf_unsupported_features(serialize(feature_writer()))
        codes = {item.value for item in report.feature_codes}
        self.assertTrue({
            "pageContentStreams", "annotations", "interactiveForms", "xfaForms",
            "embeddedFiles", "pdfPortfolio", "optionalContentLayers",
            "taggedStructure", "digitalSignatures", "javascript", "actions",
            "richMedia", "threeDimensionalContent", "unsupportedStreamFilter",
        }.issubset(codes))
        self.assertFalse(report.inspection_complete)
        self.assertFalse(report.authorizes_open)
        self.assertNotIn("PRIVATE", repr(report))
        self.assertNotIn("PRIVATE", str(report.to_dict()))
        self.assertEqual(report.feature_codes, tuple(sorted(
            set(report.feature_codes), key=lambda item: item.value
        )))

    def test_encrypted_pdf_is_reported_without_decryption(self):
        writer = blank_writer()
        writer.encrypt("PRIVATE-user-password", "PRIVATE-owner-password")
        with patch.object(PdfReader, "decrypt", side_effect=AssertionError("decrypt attempted")) as decrypt:
            report = inspect_pdf_unsupported_features(serialize(writer))
        self.assertEqual(report.feature_codes, (UnsupportedPDFFeature.ENCRYPTED_DOCUMENT,))
        self.assertFalse(report.inspection_complete)
        self.assertFalse(report.authorizes_open)
        self.assertNotIn("PRIVATE", repr(report.to_dict()))
        decrypt.assert_not_called()

    def test_xref_stream_is_identified_before_parser_construction(self):
        with patch.object(PdfReader, "__init__", side_effect=AssertionError("reader constructed")) as init:
            report = inspect_pdf_unsupported_features(xref_stream_pdf())
        self.assertEqual(report.feature_codes, (UnsupportedPDFFeature.CROSS_REFERENCE_STREAM,))
        self.assertFalse(report.inspection_complete)
        self.assertFalse(report.authorizes_open)
        init.assert_not_called()

    def test_object_streams_are_reported_without_decoding(self):
        writer = blank_writer()
        stream = DecodedStreamObject()
        stream.set_data(b"PRIVATE compressed object payload")
        stream[NameObject("/Type")] = NameObject("/ObjStm")
        stream[NameObject("/N")] = NumberObject(1)
        stream[NameObject("/First")] = NumberObject(0)
        writer._add_object(stream)
        report = inspect_pdf_unsupported_features(serialize(writer))
        self.assertIn(UnsupportedPDFFeature.OBJECT_STREAM, report.feature_codes)
        self.assertFalse(report.inspection_complete)
        self.assertFalse(report.authorizes_open)

    def test_unknown_action_type_is_reported_without_echoing_value(self):
        writer = blank_writer()
        writer._root_object[NameObject("/OpenAction")] = writer._add_object(
            DictionaryObject({
                NameObject("/S"): NameObject("/FuturePrivateAction"),
                NameObject("/Payload"): TextStringObject("PRIVATE payload"),
            })
        )
        report = inspect_pdf_unsupported_features(serialize(writer))
        self.assertIn(UnsupportedPDFFeature.UNKNOWN_ACTION_TYPE, report.feature_codes)
        self.assertNotIn("FuturePrivateAction", str(report.to_dict()))
        self.assertNotIn("PRIVATE", repr(report))

    def test_malformed_input_and_missing_parser_fail_closed(self):
        for contents in (None, "", b"", b"not a PDF", b"%PDF-1.4\n%%EOF\n",
                         serialize(blank_writer())[:-12]):
            with self.subTest(kind=type(contents).__name__), self.assertRaises(
                PDFUnsupportedFeatureInspectionError
            ) as caught:
                inspect_pdf_unsupported_features(contents)
            self.assertEqual(str(caught.exception), ERROR)
            self.assertIsNone(caught.exception.__cause__)

        original = builtins.__import__
        def no_parser(name, *args, **kwargs):
            if name == "pypdf" or name.startswith("pypdf."):
                raise ImportError("PRIVATE parser path")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=no_parser):
            with self.assertRaises(PDFUnsupportedFeatureInspectionError):
                inspect_pdf_unsupported_features(serialize(blank_writer()))

    def test_result_cannot_claim_complete_with_unsupported_features(self):
        with self.assertRaises(ValueError):
            PDFUnsupportedFeatureReport(
                (UnsupportedPDFFeature.JAVASCRIPT,), 1, True,
            )
        with self.assertRaises(ValueError):
            PDFUnsupportedFeatureReport((), 1, False)
        with self.assertRaises(FrozenInstanceError):
            PDFUnsupportedFeatureReport((), 1, True).authorizes_open = True

    def test_scanner_gate_is_not_connected_to_optional_inspector(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        source = (ROOT / "pdf_unsupported_feature_inspection.py").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_unsupported_feature_inspection", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("python3 test-pdf-unsupported-feature-inspection.py -v", ci)
        for forbidden in ("get_data(", "decrypt(", "subprocess.", "launch_clean_file(",
                          "remove_quarantine(", "write_text(", "os.environ"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
