#!/usr/bin/env python3
"""Executable parsing tests for the optional Enhanced PDF structure stage."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

from pdf_structure_parser import (
    MAX_STRUCTURE_INPUT_BYTES,
    MAX_STRUCTURE_PAGES,
    PDFStructure,
    PDFStructureParseError,
    parse_pdf_structure,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


class PDFStructureParserTests(unittest.TestCase):
    def test_parse_all_existing_harmless_reference_pdfs_with_real_library(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                before = sample.content
                structure = parse_pdf_structure(before)
                self.assertEqual(structure, PDFStructure("1.4", 1))
                self.assertIs(sample.content, before)
                self.assertTrue(sample.content.endswith(b"%%EOF\n"))
                with self.assertRaises(FrozenInstanceError):
                    structure.page_count = 0

    def test_parse_real_multipage_pdf_using_pypdf_writer(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        output = BytesIO()
        writer.write(output)
        structure = parse_pdf_structure(output.getvalue())
        self.assertEqual(structure.page_count, 2)
        self.assertRegex(structure.pdf_version, r"^1\.[0-7]$")

    def test_encrypted_documents_are_not_decrypted_or_approved(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("fixture-only-password")
        output = BytesIO()
        writer.write(output)
        with self.assertRaises(PDFStructureParseError) as failure:
            parse_pdf_structure(output.getvalue())
        self.assertEqual(
            str(failure.exception),
            "Encrypted PDF structure cannot be inspected; opening was stopped.",
        )
        self.assertNotIn("fixture-only-password", str(failure.exception))

    def test_reject_truncated_non_pdf_or_malformed_documents(self):
        cases = (
            b"",
            b"not a PDF",
            b"%PDF-1.4\n",
            b"%PDF-1.4\n%%EOF\n",
            REFERENCE_PDFS[0].content[:-10],
            b"%PDF-9.9\n%%EOF\n",
        )
        for data in cases:
            with self.subTest(contents=data[:20]):
                with self.assertRaises(PDFStructureParseError) as error:
                    parse_pdf_structure(data)
                self.assertIn("opening was stopped.", str(error.exception))
                self.assertNotIn("/private/", str(error.exception))

    def test_size_cap_and_input_type_fail_before_loading_library(self):
        self.assertGreater(MAX_STRUCTURE_INPUT_BYTES, 0)
        self.assertGreater(MAX_STRUCTURE_PAGES, 0)
        invalid = (None, True, 5, "", Path("/private/secret.pdf"),
                   bytearray(REFERENCE_PDFS[0].content),
                   memoryview(REFERENCE_PDFS[0].content))
        for value in invalid:
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(PDFStructureParseError):
                    parse_pdf_structure(value)
        with self.assertRaises(PDFStructureParseError) as error:
            parse_pdf_structure(b"x" * (MAX_STRUCTURE_INPUT_BYTES + 1))
        self.assertIn("limit", str(error.exception))

    def test_missing_pypdf_dependency_fails_closed_without_importing_on_module_load(self):
        original_import = builtins.__import__

        def reject_parser(name, *args, **kwargs):
            if name == "pypdf":
                raise ModuleNotFoundError("No module named pypdf")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=reject_parser):
            with self.assertRaises(PDFStructureParseError) as error:
                parse_pdf_structure(REFERENCE_PDFS[0].content)
        self.assertIn("parser is unavailable", str(error.exception))

    def test_parser_does_not_activate_profile_or_mutate_existing_safety_gate(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        module = (ROOT / "pdf_structure_parser.py").read_text(encoding="utf-8")
        requirements = (ROOT / "requirements-enhanced-pdf.txt").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertNotIn("pypdf", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        self.assertIn("pypdf==6.21.3", requirements)
        self.assertIn("pip install --disable-pip-version-check -r requirements-enhanced-pdf.txt", workflow)
        self.assertIn("python3 tests/pdf/structure-parser.py -v", workflow)
        for forbidden in ("subprocess.", "remove_quarantine(", "launch_clean_file(",
                          "UserDefaults", "Path(", "open(", "write_text(", "os.environ"):
            self.assertNotIn(forbidden, module)


if __name__ == "__main__":
    unittest.main()
