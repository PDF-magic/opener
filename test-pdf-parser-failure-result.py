#!/usr/bin/env python3
"""opener-0430: regression tests for structured PDF parsing failures."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

from pdf_structure_parser import (
    MAX_STRUCTURE_INPUT_BYTES,
    PDFStructure,
    PDFStructureFailureCode,
    PDFStructureParseError,
    PDFStructureParseFailure,
    parse_pdf_structure,
    parse_pdf_structure_result,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent


class PDFStructuredFailureTests(unittest.TestCase):
    def assert_failure(self, value, code):
        result = parse_pdf_structure_result(value)
        self.assertIs(type(result), PDFStructureParseFailure)
        self.assertIs(result.code, code)
        payload = result.to_dict()
        self.assertEqual(payload, {
            "schemaVersion": 1,
            "status": "failure",
            "failureCode": code.value,
            "authorizesOpen": False,
        })
        self.assertEqual(json.loads(json.dumps(payload, allow_nan=False)), payload)
        self.assertEqual(set(payload), {
            "schemaVersion", "status", "failureCode", "authorizesOpen",
        })
        with self.assertRaises(FrozenInstanceError):
            result.code = PDFStructureFailureCode.invalidStructure
        payload["failureCode"] = "forged"
        payload["authorizesOpen"] = True
        self.assertEqual(result.to_dict()["failureCode"], code.value)
        self.assertIs(result.to_dict()["authorizesOpen"], False)

    def test_success_preserves_existing_parser_evidence_contract(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                source = sample.content
                result = parse_pdf_structure_result(source)
                self.assertIs(type(result), PDFStructure)
                self.assertEqual(result, parse_pdf_structure(source))
                self.assertEqual(result.to_dict(), {
                    "schemaVersion": 1, "pdfVersion": "1.4",
                    "pageCount": 1, "authorizesOpen": False,
                })
                self.assertIs(source, sample.content)

    def test_invalid_type_and_structure_are_distinct_failures(self):
        for invalid in (None, False, 5, "", bytearray(b"%PDF-1.4"),
                        memoryview(b"%PDF-1.4"), Path("/private/sensitive.pdf")):
            with self.subTest(type=type(invalid).__name__):
                self.assert_failure(invalid, PDFStructureFailureCode.invalidInput)
        for invalid in (b"", b"not a PDF", b"%PDF-1.4\n",
                        b"%PDF-1.7\nPRIVATE_DOC_STRING\n%%EOF\n",
                        REFERENCE_PDFS[0].content[:-10]):
            with self.subTest(data=invalid[:15]):
                self.assert_failure(invalid, PDFStructureFailureCode.invalidStructure)

    def test_size_limit_and_encrypted_document_are_distinct(self):
        self.assert_failure(b"x" * (MAX_STRUCTURE_INPUT_BYTES + 1),
                            PDFStructureFailureCode.sizeLimit)
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("private-password-canary")
        output = BytesIO()
        writer.write(output)
        self.assert_failure(output.getvalue(), PDFStructureFailureCode.encrypted)

    def test_unavailable_dependency_returns_only_fixed_code(self):
        original_import = builtins.__import__

        def reject(name, *args, **kwargs):
            if name == "pypdf":
                raise ModuleNotFoundError("/private/never-log-this-document.pdf")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=reject):
            self.assert_failure(REFERENCE_PDFS[0].content,
                                PDFStructureFailureCode.dependencyUnavailable)

    def test_private_exception_details_are_not_serialized(self):
        with patch("pypdf.PdfReader",
                   side_effect=RuntimeError("RAW_CONTENT_CANARY /private/secret.pdf")):
            result = parse_pdf_structure_result(REFERENCE_PDFS[0].content)
        self.assertIs(type(result), PDFStructureParseFailure)
        self.assertEqual(result.code, PDFStructureFailureCode.invalidStructure)
        self.assertNotIn("RAW_CONTENT_CANARY", json.dumps(result.to_dict()))
        self.assertNotIn("/private/", json.dumps(result.to_dict()))
        self.assert_failure(b"%PDF-1.4\nPRIVATE_CANARY\n%%EOF\n",
                            PDFStructureFailureCode.invalidStructure)

    def test_failure_codes_cannot_be_forged_from_untrusted_pdf_text(self):
        for value in ("invalidStructure", "clean", "/private/secret.pdf",
                      None, True, 1, b"sizeLimit"):
            with self.subTest(value=repr(value)):
                with self.assertRaises(TypeError):
                    PDFStructureParseFailure(value)

    def test_exception_api_and_scanner_safety_are_unchanged(self):
        with self.assertRaises(PDFStructureParseError) as raised:
            parse_pdf_structure(b"%PDF-1.4\nBAD\n%%EOF\n")
        self.assertIn("opening was stopped.", str(raised.exception))
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        parser = (ROOT / "pdf_structure_parser.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        doc = (ROOT / "docs/pdf/structure-parser.md").read_text(encoding="utf-8")
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertNotIn("pypdf", scanner)
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("python3 test-pdf-parser-failure-result.py -v", workflow)
        self.assertIn("parse_pdf_structure_result", doc)
        for forbidden in ("open(", "subprocess.", "remove_quarantine(",
                          "launch_clean_file(", "Path(", "write_text("):
            self.assertNotIn(forbidden, parser)


if __name__ == "__main__":
    unittest.main()
