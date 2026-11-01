#!/usr/bin/env python3
"""opener-1093: deterministic regression matrix for the passive PDF parser.

Fixtures stay in memory. Structural success is not a malware verdict or an
authorization to open, and failures must not expose PDF-controlled contents.
"""

from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest
from unittest.mock import patch

from pdf_structure_parser import (
    PDFStructure,
    PDFStructureFailureCode,
    PDFStructureParseError,
    PDFStructureParseFailure,
    parse_pdf_structure,
    parse_pdf_structure_result,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]
GOOD = REFERENCE_PDFS[0].content
_ERROR = "PDF structure could not be verified; opening was stopped."


def corrupted_documents():
    """Mutate an otherwise valid PDF without introducing external payloads."""
    changes = {
        "invalid-header": GOOD.replace(b"%PDF-1.4\\n", b"%PDF-1.8\\n", 1),
        "missing-eof": GOOD.rsplit(b"%%EOF", 1)[0],
        "missing-trailer-root": GOOD.replace(b"/Root 1 0 R", b"/Xoot 1 0 R", 1),
        "empty-page-tree": GOOD.replace(b"/Count 1", b"/Count 0", 1),
        "invalid-catalog": GOOD.replace(b"/Type /Catalog", b"/Type /Invalid", 1),
    }
    for name, contents in changes.items():
        if contents == GOOD:
            raise AssertionError(f"Fixture corruption did not change {name}")
        yield name, contents


class PDFParserRegressionTests(unittest.TestCase):
    def assert_failure(self, contents):
        with self.assertRaises(PDFStructureParseError) as failure:
            parse_pdf_structure(contents)
        self.assertEqual(str(failure.exception), _ERROR)
        self.assertTrue(failure.exception.__suppress_context__)
        result = parse_pdf_structure_result(contents)
        self.assertIs(type(result), PDFStructureParseFailure)
        self.assertIs(result.code, PDFStructureFailureCode.invalidStructure)
        self.assertEqual(result.to_dict(), {
            "schemaVersion": 1,
            "status": "failure",
            "failureCode": "invalidStructure",
            "authorizesOpen": False,
        })
        self.assertNotIn("RAW_PRIVATE_CANARY", str(failure.exception))

    def test_supported_pdf_headers_produce_only_non_authorizing_evidence(self):
        for version in ("1.0", "1.1", "1.4", "1.7", "2.0"):
            with self.subTest(version=version):
                contents = GOOD.replace(
                    b"%PDF-1.4\\n", f"%PDF-{version}\\n".encode("ascii"), 1
                )
                self.assertNotEqual(contents, GOOD) if version != "1.4" else None
                direct = parse_pdf_structure(contents)
                self.assertEqual(direct, PDFStructure(version, 1))
                self.assertEqual(parse_pdf_structure_result(contents), direct)
                self.assertEqual(direct.to_dict(), {
                    "schemaVersion": 1,
                    "pdfVersion": version,
                    "pageCount": 1,
                    "authorizesOpen": False,
                })
                with self.assertRaises(FrozenInstanceError):
                    direct.page_count = 2

    def test_reference_pdf_structure_does_not_replace_scanner_verdict(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        for fixture in REFERENCE_PDFS:
            with self.subTest(fixture=fixture.identifier):
                before = fixture.content
                result = parse_pdf_structure_result(before)
                self.assertEqual(result, PDFStructure("1.4", 1))
                self.assertFalse(result.to_dict()["authorizesOpen"])
                self.assertIs(before, fixture.content)
        self.assertEqual(
            {fixture.simulated_scanner_outcome for fixture in REFERENCE_PDFS},
            {"clean", "detected", "incomplete", "failed", "timeout"},
        )

    def test_real_pdf_mutations_fail_closed_under_both_public_apis(self):
        for name, contents in corrupted_documents():
            with self.subTest(mutation=name):
                self.assert_failure(contents)

    def test_valid_parse_after_multiple_failures_is_not_poisoned(self):
        original = bytes(GOOD)
        for name, broken in corrupted_documents():
            with self.subTest(previous_failure=name):
                self.assertEqual(parse_pdf_structure(GOOD), PDFStructure("1.4", 1))
                self.assert_failure(broken)
                self.assertEqual(parse_pdf_structure_result(GOOD), PDFStructure("1.4", 1))
        self.assertEqual(GOOD, original)

    def test_library_exceptions_do_not_leak_pdf_strings_or_paths(self):
        private_text = "RAW_PRIVATE_CANARY /private/unused-document.pdf"
        with patch("pypdf.PdfReader", side_effect=RuntimeError(private_text)):
            self.assert_failure(GOOD)

    def test_ci_runs_regressions_without_wiring_parser_to_scanner(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("python3 tests/pdf/parser-regressions.py -v", workflow)
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)


if __name__ == "__main__":
    unittest.main()
