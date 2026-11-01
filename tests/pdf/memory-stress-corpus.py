#!/usr/bin/env python3
"""opener-1044: exercise memory-stress PDFs without unbounded allocations."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.generic import IndirectObject

import pdf_structure_parser as parser
from memory_stress_pdf_corpus import (
    AGGREGATE_STREAM_COUNT, DECODED_BYTES_PER_STREAM, DENSE_OBJECT_COUNT,
    MEMORY_STRESS_PDFS, REFERENCE_FANOUT,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


class MemoryStressCorpusTests(unittest.TestCase):
    def test_small_reproducible_fixtures_are_real_pdfs(self):
        self.assertEqual(
            {item.identifier for item in MEMORY_STRESS_PDFS},
            {"high-reference-fanout", "dense-object-table", "aggregate-flate-expansion"},
        )
        digests = set()
        for item in MEMORY_STRESS_PDFS:
            with self.subTest(document=item.identifier):
                content = item.generate()
                self.assertEqual(sha256(content).digest(), sha256(item.generate()).digest())
                self.assertLess(len(content), 512 * 1024)  # Never store giant binaries.
                self.assertTrue(content.startswith(b"%PDF-1.4\n"))
                self.assertTrue(content.endswith(b"%%EOF\n"))
                self.assertEqual(len(PdfReader(BytesIO(content), strict=True).pages), 1)
                for active in (b"/JavaScript", b"/JS ", b"/Launch", b"/OpenAction",
                               b"/EmbeddedFiles", b"/AA "):
                    self.assertNotIn(active, content)
                with self.assertRaises(FrozenInstanceError):
                    item.identifier = "changed"
                digests.add(sha256(content).digest())
        self.assertEqual(len(digests), len(MEMORY_STRESS_PDFS))

    def test_fixture_structures_actually_exercise_distinct_pressure(self):
        fanout = PdfReader(BytesIO(MEMORY_STRESS_PDFS[0].generate()), strict=True)
        references = fanout.trailer["/Root"]["/MemoryProbe"]
        self.assertEqual(len(references), REFERENCE_FANOUT)
        self.assertIsInstance(references[0], IndirectObject)
        self.assertEqual(references[-1].idnum, 3)

        dense = PdfReader(BytesIO(MEMORY_STRESS_PDFS[1].generate()), strict=True)
        self.assertEqual(sum(len(objects) for objects in dense.xref.values()),
                         DENSE_OBJECT_COUNT)
        self.assertEqual(DENSE_OBJECT_COUNT, parser.MAX_STRUCTURE_OBJECTS + 1)

        inflated = PdfReader(BytesIO(MEMORY_STRESS_PDFS[2].generate()), strict=True)
        self.assertEqual(AGGREGATE_STREAM_COUNT, 5)
        self.assertLess(DECODED_BYTES_PER_STREAM,
                        parser.MAX_STRUCTURE_DECOMPRESSED_STREAM_BYTES)
        self.assertGreater(AGGREGATE_STREAM_COUNT * DECODED_BYTES_PER_STREAM,
                           parser.MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES)
        for number in range(4, 4 + AGGREGATE_STREAM_COUNT):
            stream = inflated.get_object(IndirectObject(number, 0, inflated))
            self.assertEqual(stream["/Filter"], "/FlateDecode")
            self.assertEqual(len(stream.get_data()), DECODED_BYTES_PER_STREAM)

    def test_strict_parser_accepts_fanout_and_rejects_memory_budgets(self):
        fanout = parser.parse_pdf_structure_result(MEMORY_STRESS_PDFS[0].generate())
        self.assertIsInstance(fanout, parser.PDFStructure)
        self.assertEqual(fanout.page_count, 1)
        self.assertFalse(fanout.to_dict()["authorizesOpen"])
        for item in MEMORY_STRESS_PDFS[1:]:
            with self.subTest(document=item.identifier):
                outcome = parser.parse_pdf_structure_result(item.generate())
                self.assertIsInstance(outcome, parser.PDFStructureParseFailure)
                self.assertIs(outcome.code, parser.PDFStructureFailureCode.sizeLimit)
                self.assertEqual(outcome.to_dict()["status"], "failure")
                self.assertFalse(outcome.to_dict()["authorizesOpen"])

    def test_budget_boundaries_are_independent_and_fail_closed(self):
        # Each input is valid; rejection is specifically a configured resource
        # budget, not malformed xref entries or an oversized individual stream.
        with patch.object(parser, "MAX_STRUCTURE_TOTAL_DECOMPRESSED_BYTES",
                          40 * 1024 * 1024):
            self.assertEqual(
                parser.parse_pdf_structure(MEMORY_STRESS_PDFS[2].generate()).page_count, 1
            )

    def test_corpus_is_isolated_from_scanner_and_wired_into_ci(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertTrue({item.identifier for item in REFERENCE_PDFS}.isdisjoint(
            item.identifier for item in MEMORY_STRESS_PDFS
        ))
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("memory_stress_pdf_corpus", scanner)
        self.assertIn("verify_file_integrity", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/memory-stress-corpus.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
