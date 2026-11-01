#!/usr/bin/env python3
"""opener-1032: malformed PDF object-stream security corpus regressions."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import unittest

from pypdf import PdfReader
from pypdf.generic import IndirectObject

from malformed_object_stream_corpus import (
    MALFORMED_OBJECT_STREAM_PDFS,
    VALID_OBJECT_STREAM_PDFS,
)
from pdf_structure_parser import (
    PDFStructure,
    PDFStructureFailureCode,
    PDFStructureParseError,
    PDFStructureParseFailure,
    parse_pdf_structure,
    parse_pdf_structure_result,
)
from protection_profiles import ProtectionProfileID, protection_profile_definition
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]
BLOCK_MESSAGE = "PDF structure could not be verified; opening was stopped."


class MalformedObjectStreamCorpusTests(unittest.TestCase):
    def test_valid_object_stream_controls_resolve_compressed_page(self):
        self.assertEqual(len(VALID_OBJECT_STREAM_PDFS), 2)
        for fixture in VALID_OBJECT_STREAM_PDFS:
            with self.subTest(fixture=fixture.identifier):
                source = fixture.content
                reader = PdfReader(BytesIO(source), strict=True)
                self.assertEqual(reader.xref_objStm[3], (4, 0))
                self.assertEqual(reader.get_object(IndirectObject(3, 0, reader))["/Type"], "/Page")
                self.assertEqual(parse_pdf_structure(source), PDFStructure("1.5", 1))
                self.assertIs(fixture.content, source)

    def test_malformed_collection_has_distinct_real_pdf_object_streams(self):
        self.assertEqual(len(MALFORMED_OBJECT_STREAM_PDFS), 8)
        corpus = VALID_OBJECT_STREAM_PDFS + MALFORMED_OBJECT_STREAM_PDFS
        self.assertEqual(len({fixture.identifier for fixture in corpus}), len(corpus))
        self.assertEqual(len({sha256(fixture.content).digest() for fixture in corpus}), len(corpus))
        for fixture in corpus:
            with self.subTest(fixture=fixture.identifier):
                source = fixture.content
                self.assertTrue(source.startswith(b"%PDF-1.5\n"))
                self.assertTrue(source.endswith(b"%%EOF\n"))
                self.assertIn(b"/Type /ObjStm", source)
                self.assertIn(b"/Type /XRef", source)
                self.assertNotIn(b"3 0 obj\n", source, "No uncompressed page fallback")
                self.assertIn(b"/Kids [3 0 R]", source)
                self.assertIn(b"4 0 obj\n", source)
                startxref = int(source.rsplit(b"startxref\n", 1)[1].splitlines()[0])
                self.assertTrue(source[startxref:].startswith(b"5 0 obj\n<< /Type /XRef"))
                self.assertIs(source, fixture.content)

    def test_each_malformed_object_stream_fails_closed_without_a_verdict(self):
        for fixture in MALFORMED_OBJECT_STREAM_PDFS:
            with self.subTest(fixture=fixture.identifier):
                source = fixture.content
                with self.assertRaises(PDFStructureParseError) as raised:
                    parse_pdf_structure(source)
                self.assertEqual(str(raised.exception), BLOCK_MESSAGE)
                failure = parse_pdf_structure_result(source)
                self.assertIs(type(failure), PDFStructureParseFailure)
                self.assertIs(failure.code, PDFStructureFailureCode.invalidStructure)
                self.assertEqual(failure.to_dict(), {
                    "schemaVersion": 1, "status": "failure",
                    "failureCode": "invalidStructure", "authorizesOpen": False,
                })
                self.assertIs(fixture.content, source)

    def test_no_existing_reference_or_scanner_settings_are_modified(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertTrue(all(sample.content.startswith(b"%PDF-1.4\n") for sample in REFERENCE_PDFS))
        self.assertFalse(protection_profile_definition(ProtectionProfileID.ENHANCED).selectable)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("malformed_object_stream_corpus", scanner)
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/malformed-object-stream-corpus.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
