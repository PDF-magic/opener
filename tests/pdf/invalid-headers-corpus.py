#!/usr/bin/env python3
"""opener-1029: invalid PDF headers in the deterministic security test corpus.

Only header bytes are corrupted; valid objects and trailer remain unchanged.
Tests use passive identification and structural-failure evidence, never
claim an antivirus scan or permit opening a file.
"""

from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from pdf_format_identification import (
    NOT_PDF, UNDETERMINED, identify_pdf_format, identify_pdf_header,
)
from pdf_structure_parser import (
    PDFStructureFailureCode, PDFStructureParseFailure, parse_pdf_structure_result,
)
from reference_pdf_collection import INVALID_PDF_HEADERS, REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


class InvalidPDFHeaderCorpusTests(unittest.TestCase):
    def test_only_header_is_corrupted_and_each_fixture_is_unique(self):
        baseline = REFERENCE_PDFS[0].content
        self.assertEqual(baseline[:9], b"%PDF-1.4\n")
        self.assertEqual(len(INVALID_PDF_HEADERS), 9)
        self.assertEqual(len({case.identifier for case in INVALID_PDF_HEADERS}), 9)
        self.assertEqual(len({sha256(case.content).digest()
                              for case in INVALID_PDF_HEADERS}), 9)
        self.assertEqual({case.expected_header_status for case in INVALID_PDF_HEADERS},
                         {"notPdf", "undetermined"})
        for case in INVALID_PDF_HEADERS:
            with self.subTest(case=case.identifier):
                self.assertIs(type(case.content), bytes)
                self.assertEqual(len(case.content), len(baseline))
                self.assertNotEqual(case.content[:9], baseline[:9])
                self.assertEqual(case.content[9:], baseline[9:])
                self.assertTrue(case.content.endswith(b"%%EOF\n"))
                self.assertIn(b"trailer\n", case.content)
                with self.assertRaises(FrozenInstanceError):
                    case.identifier = "changed"

    def test_invalid_headers_never_produce_positive_pdf_identification(self):
        with tempfile.TemporaryDirectory(prefix="invalid-pdf-headers-") as directory:
            for case in INVALID_PDF_HEADERS:
                expected = NOT_PDF if case.expected_header_status == "notPdf" else UNDETERMINED
                with self.subTest(case=case.identifier):
                    self.assertIs(identify_pdf_header(case.content), expected)
                    for suffix in (".pdf", ".bin"):
                        source = Path(directory) / (case.identifier + suffix)
                        source.write_bytes(case.content)
                        before = sha256(source.read_bytes()).digest()
                        evidence = identify_pdf_format(source)
                        self.assertIs(evidence, expected)
                        self.assertFalse(evidence.permits_open)
                        self.assertEqual(sha256(source.read_bytes()).digest(), before)

    def test_invalid_headers_fail_strict_structure_even_with_valid_body(self):
        for case in INVALID_PDF_HEADERS:
            with self.subTest(case=case.identifier):
                evidence = parse_pdf_structure_result(case.content)
                self.assertIs(type(evidence), PDFStructureParseFailure)
                self.assertIs(evidence.code, PDFStructureFailureCode.invalidStructure)
                self.assertEqual(evidence.to_dict()["status"], "failure")
                self.assertIs(evidence.to_dict()["authorizesOpen"], False)
                self.assertNotIn(case.identifier, repr(evidence))

    def test_valid_reference_pdf_and_existing_safety_boundaries_are_preserved(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        for case in REFERENCE_PDFS:
            self.assertEqual(identify_pdf_header(case.content).version, "1.4")
            self.assertFalse(identify_pdf_header(case.content).permits_open)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("INVALID_PDF_HEADERS", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/invalid-headers-corpus.py -v",
                      workflow)


if __name__ == "__main__":
    unittest.main()
