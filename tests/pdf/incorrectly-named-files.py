#!/usr/bin/env python3
"""opener-1028: wrongly named files for the PDF security test corpus."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
import unittest

from pdf_format_identification import PDFFormatStatus, identify_pdf_format
from pdf_structure_parser import PDFStructureParseError, parse_pdf_structure
from reference_pdf_collection import INCORRECTLY_NAMED_FILES, REFERENCE_PDFS


class IncorrectlyNamedFileCorpusTests(unittest.TestCase):
    def test_valid_pdfs_with_incorrect_extensions_keep_their_pdf_identity(self):
        with tempfile.TemporaryDirectory(prefix="misnamed-pdf-") as directory:
            root = Path(directory)
            for sample in INCORRECTLY_NAMED_FILES:
                if not sample.is_pdf:
                    continue
                with self.subTest(name=sample.filename):
                    path = root / sample.filename
                    path.write_bytes(sample.content)
                    before = path.read_bytes()

                    identified = identify_pdf_format(path)
                    self.assertIs(identified.status, PDFFormatStatus.PDF_HEADER)
                    self.assertEqual(identified.media_type, "application/pdf")
                    self.assertEqual(identified.version, "1.4")
                    self.assertEqual(parse_pdf_structure(before).page_count, 1)
                    self.assertFalse(identified.permits_open)
                    self.assertEqual(path.read_bytes(), before)

    def test_non_pdf_bytes_with_pdf_names_cannot_spoof_a_pdf(self):
        with tempfile.TemporaryDirectory(prefix="misnamed-spoof-") as directory:
            root = Path(directory)
            for sample in INCORRECTLY_NAMED_FILES:
                if sample.is_pdf:
                    continue
                with self.subTest(name=sample.filename):
                    path = root / sample.filename
                    path.write_bytes(sample.content)
                    before = path.read_bytes()

                    identified = identify_pdf_format(path)
                    self.assertIs(identified.status, PDFFormatStatus.NOT_PDF)
                    self.assertFalse(identified.permits_open)
                    with self.assertRaises(PDFStructureParseError):
                        parse_pdf_structure(before)
                    self.assertEqual(path.read_bytes(), before)

    def test_corpus_covers_both_directions_and_preserves_reference_pdfs(self):
        names = [item.filename for item in INCORRECTLY_NAMED_FILES]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertEqual(
            {name for name, item in zip(names, INCORRECTLY_NAMED_FILES) if item.is_pdf},
            {"real-pdf.txt", "real-pdf.png", "real-pdf.pdf.txt",
             "real-pdf-no-extension", "real-pdf.PDF"},
        )
        self.assertEqual(
            {item.filename for item in INCORRECTLY_NAMED_FILES if not item.is_pdf},
            {"plain-text.pdf", "png-header.pdf", "embedded-pdf-header.pdf"},
        )
        for item in INCORRECTLY_NAMED_FILES:
            with self.subTest(name=item.filename):
                self.assertIsInstance(item.content, bytes)
                self.assertNotIn("/", item.filename)
                with self.assertRaises(FrozenInstanceError):
                    item.filename = "overwritten"

    def test_only_test_corpus_changes_not_installed_scanner(self):
        root = Path(__file__).resolve().parents[2]
        scanner = (root / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("INCORRECTLY_NAMED_FILES", scanner)
        self.assertNotIn("pdf_format_identification", scanner)
        ci = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/pdf/incorrectly-named-files.py -v", ci)


if __name__ == "__main__":
    unittest.main()
