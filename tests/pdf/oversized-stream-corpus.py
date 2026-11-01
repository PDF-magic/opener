#!/usr/bin/env python3
"""opener-1042: verify real oversized embedded-stream PDF corpus fixtures."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import socket
import subprocess
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.generic import IndirectObject, StreamObject

from oversized_stream_corpus import (
    OVERSIZED_STREAM_PDFS, STREAM_LIMIT, _embedded_pdf,
)
from pdf_embedded_object_sizes import (
    LARGE_DECLARED_BYTES, LARGE_DECODED_BYTES, LARGE_ENCODED_BYTES,
    inspect_pdf_embedded_object_sizes,
)
from pdf_structure_parser import PDFStructure, parse_pdf_structure
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


class OversizedStreamCorpusTests(unittest.TestCase):
    def test_four_distinct_deterministic_complete_pdfs(self):
        self.assertEqual(len(OVERSIZED_STREAM_PDFS), 4)
        self.assertEqual(len({case.identifier for case in OVERSIZED_STREAM_PDFS}), 4)
        self.assertEqual(len({sha256(case.content).digest()
                              for case in OVERSIZED_STREAM_PDFS}), 4)
        self.assertEqual(STREAM_LIMIT, LARGE_ENCODED_BYTES)
        self.assertEqual(STREAM_LIMIT, LARGE_DECODED_BYTES)
        self.assertEqual(STREAM_LIMIT, LARGE_DECLARED_BYTES)
        for case in OVERSIZED_STREAM_PDFS:
            with self.subTest(case=case.identifier):
                self.assertEqual(type(case.content), bytes)
                self.assertTrue(case.content.startswith(b"%PDF-1."))
                self.assertTrue(case.content.rstrip().endswith(b"%%EOF"))
                self.assertEqual(len(PdfReader(BytesIO(case.content), strict=True).pages), 1)
                self.assertEqual(parse_pdf_structure(case.content), PDFStructure("1.3", 1))
                for forbidden in (b"/JavaScript", b"/Launch", b"/OpenAction", b"/AA "):
                    self.assertNotIn(forbidden, case.content)
                with self.assertRaises(FrozenInstanceError):
                    case.content = b"changed"

        self.assertEqual(OVERSIZED_STREAM_PDFS[0].content,
                         _embedded_pdf(b"A" * (STREAM_LIMIT + 1)))
        self.assertEqual(OVERSIZED_STREAM_PDFS[1].content,
                         _embedded_pdf(b"B" * (2 * STREAM_LIMIT + 1), compressed=True))

    def test_genuine_embedded_file_streams_and_length_boundaries(self):
        for index, case in enumerate(OVERSIZED_STREAM_PDFS):
            with self.subTest(case=case.identifier):
                reader = PdfReader(BytesIO(case.content), strict=True)
                if index == 2:
                    self.assertNotIn("/Names", reader.trailer["/Root"])
                    objects = [reader.get_object(IndirectObject(n, 0, reader))
                               for n in reader.xref[0] if n]
                    embedded = [obj for obj in objects
                                if isinstance(obj, StreamObject)
                                and obj.get("/Type") == "/EmbeddedFile"]
                    self.assertEqual(len(embedded), 1)
                    stream = embedded[0]
                else:
                    spec = reader.trailer["/Root"]["/Names"]["/EmbeddedFiles"]["/Names"][1]
                    stream = spec.get_object()["/EF"]["/F"].get_object()
                    self.assertIsInstance(stream, StreamObject)
                if index in (0, 2):
                    self.assertEqual(len(stream._data), STREAM_LIMIT + 1)
                elif index == 1:
                    self.assertEqual(stream["/Filter"], "/FlateDecode")
                    self.assertLess(len(stream._data), STREAM_LIMIT)
                    self.assertEqual(len(stream.get_data()), 2 * STREAM_LIMIT + 1)
                else:
                    self.assertEqual(stream["/Params"]["/Size"], 4 * STREAM_LIMIT)
                    self.assertEqual(stream.get_data(), b"harmless fixture")

    def test_bounded_inspector_reports_oversize_without_authorizing_open(self):
        with (patch.object(socket, "create_connection") as network,
              patch.object(subprocess, "Popen") as process):
            for case in OVERSIZED_STREAM_PDFS:
                with self.subTest(case=case.identifier):
                    result = inspect_pdf_embedded_object_sizes(case.content)
                    self.assertEqual(result.embedded_stream_count, 1)
                    self.assertEqual(result.large_encoded_count, case.expected_large_encoded)
                    self.assertEqual(result.large_decoded_count, case.expected_large_decoded)
                    self.assertEqual(result.high_expansion_count, case.expected_high_expansion)
                    self.assertEqual(result.large_declared_count, case.expected_large_declared)
                    self.assertTrue(result.has_large_objects)
                    self.assertFalse(result.permits_open)
                    self.assertNotIn("synthetic-fixture", repr(result))
            network.assert_not_called()
            process.assert_not_called()

    def test_reference_corpus_and_existing_scanner_are_unmodified(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertTrue({case.identifier for case in OVERSIZED_STREAM_PDFS}
                        .isdisjoint(case.identifier for case in REFERENCE_PDFS))
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        self.assertNotIn("oversized_stream_corpus", scanner)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/oversized-stream-corpus.py -v", ci)


if __name__ == "__main__":
    unittest.main()
