#!/usr/bin/env python3
"""opener-0445: inspect real XFA form entries without executing or decoding XML."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject, DecodedStreamObject, DictionaryObject, NameObject,
    NumberObject, TextStringObject,
)

from pdf_xfa_forms import (
    MAX_XFA_PACKETS, PDFXFAInspection, PDFXFAInspectionError,
    inspect_pdf_xfa_forms,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent
_FAILURE = "PDF XFA forms could not be fully inspected; opening was stopped."


def writer_with_page():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    return writer


def document(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def packet_stream(payload=b"<xfa:template>private-contents</xfa:template>"):
    stream = DecodedStreamObject()
    stream.set_data(payload)
    return stream


def with_xfa(xfa, *, indirect_form=True):
    writer = writer_with_page()
    form = DictionaryObject({
        NameObject("/Fields"): ArrayObject(),
        NameObject("/XFA"): xfa,
    })
    writer._root_object[NameObject("/AcroForm")] = (
        writer._add_object(form) if indirect_form else form
    )
    return document(writer)


class PDFXFAFormTests(unittest.TestCase):
    def test_reference_documents_and_regular_acroforms_do_not_claim_xfa(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                result = inspect_pdf_xfa_forms(sample.content)
                self.assertEqual(result, PDFXFAInspection("none", 0))
                self.assertFalse(result.contains_xfa)
                self.assertFalse(result.permits_open)
        writer = writer_with_page()
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject(),
        })
        self.assertEqual(
            inspect_pdf_xfa_forms(document(writer)), PDFXFAInspection("none", 0)
        )

    def test_single_xfa_stream_is_detected_without_exposing_xml(self):
        writer = writer_with_page()
        writer._root_object[NameObject("/AcroForm")] = writer._add_object(
            DictionaryObject({
                NameObject("/Fields"): ArrayObject(),
                NameObject("/XFA"): writer._add_object(
                    packet_stream(b"<xfa:datasets>PRIVATE_CANARY</xfa:datasets>")
                ),
            })
        )
        result = inspect_pdf_xfa_forms(document(writer))
        self.assertEqual(result, PDFXFAInspection("stream", 0))
        self.assertTrue(result.contains_xfa)
        self.assertIs(result.to_dict()["authorizesOpen"], False)
        self.assertNotIn("PRIVATE_CANARY", repr(result))
        self.assertNotIn("PRIVATE_CANARY", json.dumps(result.to_dict()))

    def test_array_of_named_packets_is_detected_with_bounded_count(self):
        writer = writer_with_page()
        template = writer._add_object(packet_stream(b"<template>private</template>"))
        datasets = writer._add_object(packet_stream(b"<datasets>secret</datasets>"))
        xfa = ArrayObject([
            TextStringObject("template"), template,
            TextStringObject("datasets"), datasets,
        ])
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject(),
            NameObject("/XFA"): writer._add_object(xfa),
        })
        evidence = inspect_pdf_xfa_forms(document(writer))
        self.assertEqual(evidence, PDFXFAInspection("packets", 2))
        self.assertEqual(evidence.to_dict(), {
            "schemaVersion": 1, "containsXFA": True,
            "representation": "packets", "packetCount": 2,
            "authorizesOpen": False,
        })
        self.assertEqual(json.loads(json.dumps(evidence.to_dict())), evidence.to_dict())
        output = evidence.to_dict()
        output["authorizesOpen"] = True
        output["packetCount"] = 9999
        self.assertIs(evidence.to_dict()["authorizesOpen"], False)
        self.assertEqual(evidence.packet_count, 2)
        with self.assertRaises(FrozenInstanceError):
            evidence.packet_count = 99

    def test_direct_form_and_single_packet_array_are_supported(self):
        writer = writer_with_page()
        xfa = ArrayObject([
            TextStringObject("template"),
            writer._add_object(packet_stream(b"<template/>")),
        ])
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/Fields"): ArrayObject(),
            NameObject("/XFA"): xfa,
        })
        self.assertEqual(
            inspect_pdf_xfa_forms(document(writer)), PDFXFAInspection("packets", 1)
        )

    def assert_rejected(self, data):
        with self.assertRaises(PDFXFAInspectionError) as caught:
            inspect_pdf_xfa_forms(data)
        self.assertEqual(str(caught.exception), _FAILURE)

    def test_invalid_xfa_shapes_fail_closed_without_exposing_payloads(self):
        for invalid in (
            NumberObject(3),
            TextStringObject("secret should not appear"),
            ArrayObject(),
            ArrayObject([TextStringObject("odd")]),
            ArrayObject([TextStringObject("template"), NumberObject(2)]),
            ArrayObject([NumberObject(2), packet_stream()]),
            ArrayObject([TextStringObject(""), packet_stream()]),
            ArrayObject([TextStringObject("X" * 129), packet_stream()]),
        ):
            with self.subTest(shape=type(invalid).__name__, description=str(invalid)[:14]):
                self.assert_rejected(with_xfa(invalid))
        writer = writer_with_page()
        writer._root_object[NameObject("/AcroForm")] = NumberObject(7)
        self.assert_rejected(document(writer))

    def test_excessive_xfa_packet_count_fails_closed(self):
        writer = writer_with_page()
        shared = writer._add_object(packet_stream(b"<data/>"))
        entries = ArrayObject()
        for _ in range(MAX_XFA_PACKETS + 1):
            entries.extend([TextStringObject("template"), shared])
        writer._root_object[NameObject("/AcroForm")] = DictionaryObject({
            NameObject("/XFA"): entries,
        })
        self.assert_rejected(document(writer))

    def test_invalid_metadata_cannot_be_forged_into_open_verdict(self):
        for representation, count in (
            ("other", 1), ("none", 1), ("stream", 1), ("packets", 0),
            ("packets", MAX_XFA_PACKETS + 1), (1, 0), ("none", True),
        ):
            with self.subTest(representation=repr(representation), count=count):
                with self.assertRaises(ValueError):
                    PDFXFAInspection(representation, count)
        with self.assertRaises(TypeError):
            PDFXFAInspection("none", 0, True)

    def test_malformed_encrypted_oversize_and_missing_parser_fail_closed(self):
        writer = writer_with_page()
        writer.encrypt("fixture-password-do-not-echo")
        for invalid in (
            document(writer), b"not-a-pdf", b"%PDF-1.4\n%%EOF\n", None,
            bytearray(b"%PDF-1.4\n"), b"z" * (16 * 1024 * 1024 + 1),
        ):
            with self.subTest(kind=type(invalid).__name__):
                self.assert_rejected(invalid)
        original_import = builtins.__import__

        def missing(name, *args, **kwargs):
            if name == "pypdf":
                raise ModuleNotFoundError("/private/xfa-document.pdf")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=missing):
            self.assert_rejected(REFERENCE_PDFS[0].content)

    def test_new_inspector_does_not_activate_scanner_or_read_xfa_content(self):
        source = (ROOT / "pdf_xfa_forms.py").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        docs = (ROOT / "docs/pdf/xfa-forms.md").read_text(encoding="utf-8")
        self.assertNotIn("pdf_xfa_forms", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("python3 scripts/run-test.py tests/pdf/xfa-forms.py -v", ci)
        self.assertIn("/AcroForm", docs)
        self.assertIn("/XFA", docs)
        for forbidden in ("get_data(", "decompress(", "open(", "subprocess.",
                          "os.environ", "write_text(", "remove_quarantine(",
                          "launch_clean_file("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
