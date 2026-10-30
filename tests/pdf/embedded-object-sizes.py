#!/usr/bin/env python3
"""opener-0458: suspiciously large PDF object evidence remains non-opening."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import builtins
import socket
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
)
import pdf_embedded_object_sizes as stage
from pdf_embedded_object_sizes import (
    BLOCK_MESSAGE, PDFEmbeddedObjectSizeError, PDFEmbeddedObjectSizes,
    inspect_pdf_embedded_object_sizes,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


def document(writer):
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def writer_with_attachment(payload, *, compress=False, declared=None):
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_attachment("private-report.bin", payload)
    spec = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()
    stream = spec["/EF"]["/F"].get_object()
    if compress:
        compressed = stream.flate_encode()
        # Preserve the same attachment reference and its PDF object number.
        stream._data = compressed._data
        stream[NameObject("/Filter")] = NameObject("/FlateDecode")
    if declared is not None:
        stream[NameObject("/Params")] = DictionaryObject({
            NameObject("/Size"): NumberObject(declared),
        })
    return writer


class EmbeddedObjectSizeTests(unittest.TestCase):
    def assert_blocked(self, data):
        with self.assertRaises(PDFEmbeddedObjectSizeError) as raised:
            inspect_pdf_embedded_object_sizes(data)
        self.assertEqual(str(raised.exception), BLOCK_MESSAGE)
        self.assertIsNone(raised.exception.__cause__)

    def test_reference_corpus_and_small_attachments_are_non_authorizing(self):
        for pdf in REFERENCE_PDFS:
            with self.subTest(name=pdf.identifier):
                result = inspect_pdf_embedded_object_sizes(pdf.content)
                self.assertFalse(result.has_large_objects)
                self.assertEqual(result.embedded_stream_count, 0)
                self.assertFalse(result.permits_open)
        result = inspect_pdf_embedded_object_sizes(
            document(writer_with_attachment(b"safe sample bytes")))
        self.assertEqual(result.embedded_stream_count, 1)
        self.assertFalse(result.has_large_objects)
        with self.assertRaises(FrozenInstanceError):
            result.permits_open = True

    def test_large_raw_stream_and_attachment_are_detected_without_extraction(self):
        payload = b"PRIVATE_DATA" * 100000
        writer = writer_with_attachment(payload)
        with (
            patch.object(socket, "getaddrinfo") as dns,
            patch.object(subprocess, "run") as spawn,
            patch.object(Path, "open") as file_open,
        ):
            result = inspect_pdf_embedded_object_sizes(document(writer))
        self.assertEqual(result.embedded_stream_count, 1)
        self.assertEqual(result.large_encoded_count, 1)
        self.assertEqual(result.large_decoded_count, 1)
        self.assertFalse(result.permits_open)
        self.assertNotIn("PRIVATE", repr(result))
        dns.assert_not_called()
        spawn.assert_not_called()
        file_open.assert_not_called()

    def test_large_compressed_attachment_is_detected_with_bounded_inflation(self):
        writer = writer_with_attachment(b"A" * (2 * 1024 * 1024), compress=True)
        result = inspect_pdf_embedded_object_sizes(document(writer))
        self.assertEqual(result.embedded_stream_count, 1)
        self.assertEqual(result.large_encoded_count, 0)
        self.assertEqual(result.large_decoded_count, 1)
        self.assertEqual(result.high_expansion_count, 1)

    def test_unreferenced_embedded_stream_is_detected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=200, height=200)
        stream = DecodedStreamObject()
        stream.set_data(b"X" * (1024 * 1024 + 1))
        stream[NameObject("/Type")] = NameObject("/EmbeddedFile")
        writer._add_object(stream)
        result = inspect_pdf_embedded_object_sizes(document(writer))
        self.assertEqual(result.embedded_stream_count, 1)
        self.assertEqual(result.large_encoded_count, 1)
        self.assertEqual(result.large_decoded_count, 1)

    def test_declared_oversize_is_evidence_not_an_open_permission(self):
        result = inspect_pdf_embedded_object_sizes(document(
            writer_with_attachment(b"regular data", declared=4 * 1024 * 1024)
        ))
        self.assertEqual(result.large_declared_count, 1)
        self.assertFalse(result.permits_open)

    def test_distinct_f_and_uf_stream_references_are_both_inspected(self):
        writer = writer_with_attachment(b"safe")
        spec = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()
        big = DecodedStreamObject()
        big.set_data(b"B" * (1024 * 1024 + 1))
        ref = writer._add_object(big)
        spec["/EF"][NameObject("/UF")] = ref
        result = inspect_pdf_embedded_object_sizes(document(writer))
        self.assertEqual(result.embedded_stream_count, 2)
        self.assertEqual(result.large_encoded_count, 1)
        self.assertEqual(result.large_decoded_count, 1)

    def test_bad_structure_missing_and_invalid_streams_fail_closed(self):
        writer = writer_with_attachment(b"safe")
        spec = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()
        spec["/EF"][NameObject("/F")] = NumberObject(12)
        self.assert_blocked(document(writer))
        writer = writer_with_attachment(b"safe")
        stream = writer._root_object["/Names"]["/EmbeddedFiles"]["/Names"][1].get_object()["/EF"]["/F"].get_object()
        stream[NameObject("/Params")] = DictionaryObject({
            NameObject("/Size"): NameObject("/bad"),
        })
        self.assert_blocked(document(writer))
        writer = writer_with_attachment(b"safe")
        writer.encrypt("synthetic-only")
        self.assert_blocked(document(writer))
        for data in (None, "string", b"", b"garbage"):
            self.assert_blocked(data)

    def test_bounds_and_result_validation(self):
        with patch.object(stage, "MAX_STREAMS", 0):
            self.assert_blocked(document(writer_with_attachment(b"small")))
        with self.assertRaises(ValueError):
            PDFEmbeddedObjectSizes(0, 1, 0, 0, 0, 0)
        with self.assertRaises(ValueError):
            PDFEmbeddedObjectSizes(1, 1, 0, 2, 0, 0)
        with self.assertRaises(ValueError):
            PDFEmbeddedObjectSizes(True, 0, 0, 0, 0, 0)

    def test_scanner_integrity_and_ci_coverage(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_embedded_object_sizes", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("python3 tests/pdf/embedded-object-sizes.py -v", workflow)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
