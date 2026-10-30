#!/usr/bin/env python3
"""opener-0413: enforce the optional PDF parser's structured output contract."""

from dataclasses import FrozenInstanceError
from io import BytesIO
import json
from pathlib import Path
import unittest

from pypdf import PdfWriter

from pdf_structure_parser import (
    MAX_STRUCTURE_PAGES,
    PDFStructure,
    PDFStructureParseError,
    parse_pdf_structure,
)

ROOT = Path(__file__).resolve().parent
SCHEMA_KEYS = {"schemaVersion", "pdfVersion", "pageCount", "authorizesOpen"}


class PDFParserOutputTests(unittest.TestCase):
    def test_real_parser_produces_bounded_versioned_evidence(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        output = BytesIO()
        writer.write(output)

        evidence = parse_pdf_structure(output.getvalue())
        self.assertIs(type(evidence), PDFStructure)
        self.assertEqual(evidence.page_count, 2)
        record = evidence.to_dict()
        self.assertEqual(set(record), SCHEMA_KEYS)
        self.assertEqual(record["schemaVersion"], 1)
        self.assertEqual(record["pdfVersion"], evidence.pdf_version)
        self.assertEqual(record["pageCount"], 2)
        self.assertIs(record["authorizesOpen"], False)
        self.assertEqual(json.loads(json.dumps(record, allow_nan=False)), record)
        # Never include content, a path, decoded strings, or a clean verdict.
        self.assertEqual(
            set(record.values()) & {str(output.getvalue()), "clean", "approved"},
            set(),
        )

    def test_detached_output_cannot_mutate_verified_evidence(self):
        evidence = PDFStructure("2.0", 1)
        with self.assertRaises(FrozenInstanceError):
            evidence.page_count = 500
        first = evidence.to_dict()
        first.update({"pageCount": 999, "authorizesOpen": True,
                      "documentPath": "/private/example.pdf"})
        self.assertEqual(evidence.to_dict(), {
            "schemaVersion": 1, "pdfVersion": "2.0",
            "pageCount": 1, "authorizesOpen": False,
        })

    def test_constructor_rejects_untrusted_or_unbounded_metadata(self):
        for version in (None, b"1.7", "", "1.8", "3.0", "1.7\x00secret",
                        "/private/document.pdf", True, 1.7, "2.0/JavaScript"):
            with self.subTest(version=repr(version)):
                with self.assertRaises(ValueError):
                    PDFStructure(version, 1)
        for count in (None, 0, -1, MAX_STRUCTURE_PAGES + 1, True, False,
                      1.0, "1", b"1", float("nan")):
            with self.subTest(count=repr(count)):
                with self.assertRaises(ValueError):
                    PDFStructure("1.7", count)
        for version in (*[f"1.{minor}" for minor in range(8)], "2.0"):
            with self.subTest(accepted=version):
                self.assertEqual(PDFStructure(version, MAX_STRUCTURE_PAGES).page_count,
                                 MAX_STRUCTURE_PAGES)

    def test_malformed_pdf_has_no_successful_structured_output(self):
        private_marker = b"PRIVATE_CONTENT_SHOULD_NOT_APPEAR"
        malformed = b"%PDF-1.7\n" + private_marker + b"\n%%EOF\n"
        with self.assertRaises(PDFStructureParseError) as caught:
            parse_pdf_structure(malformed)
        self.assertNotIn(private_marker.decode("ascii"), str(caught.exception))
        self.assertNotIn("authorizesOpen", str(caught.exception))

    def test_contract_is_optional_and_ci_runs_the_regression(self):
        source = (ROOT / "pdf_structure_parser.py").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        docs = (ROOT / "docs/pdf/structure-parser.md").read_text(encoding="utf-8")
        self.assertIn("python3 test-pdf-parser-output.py -v", ci)
        self.assertIn("schemaVersion", docs)
        self.assertIn("authorizesOpen", docs)
        self.assertIn("MAX_STRUCTURE_PAGES", source)
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertNotIn("pypdf", scanner)
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
        self.assertIn("check_database()", scanner)


if __name__ == "__main__":
    unittest.main()
