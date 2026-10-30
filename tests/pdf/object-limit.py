#!/usr/bin/env python3
"""opener-0431: reject PDF object indexes above the parser's total budget."""

from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from pdf_structure_parser import (
    MAX_STRUCTURE_OBJECTS, PDFStructure, PDFStructureParseError,
    parse_pdf_structure,
)

ROOT = Path(__file__).resolve().parent
LIMIT_MESSAGE = "The PDF exceeds the structure inspection limit; opening was stopped."


def make_indexed_pdf(objects):
    """In-memory one-page PDF with exact xref offsets and inert extra objects."""
    assert objects >= 3
    document = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number in range(1, objects + 1):
        offsets.append(len(document))
        if number == 1:
            body = b"<< /Type /Catalog /Pages 2 0 R >>"
        elif number == 2:
            body = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
        elif number == 3:
            body = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>"
        else:
            body = b"null"  # Unreferenced objects must still count.
        document.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(document)
    document.extend(f"xref\n0 {objects + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        document.extend(f"{offset:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size {objects + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(document)


class PDFObjectLimitTests(unittest.TestCase):
    def test_exact_boundary_allows_valid_pdf_with_unreferenced_objects(self):
        self.assertEqual(MAX_STRUCTURE_OBJECTS, 4096)
        for count in (3, MAX_STRUCTURE_OBJECTS - 1, MAX_STRUCTURE_OBJECTS):
            with self.subTest(count=count):
                self.assertEqual(
                    parse_pdf_structure(make_indexed_pdf(count)),
                    PDFStructure("1.4", 1),
                )

    def test_one_extra_object_fails_closed(self):
        for count in (MAX_STRUCTURE_OBJECTS + 1, MAX_STRUCTURE_OBJECTS + 8):
            with self.subTest(count=count):
                with self.assertRaises(PDFStructureParseError) as error:
                    parse_pdf_structure(make_indexed_pdf(count))
                self.assertEqual(str(error.exception), LIMIT_MESSAGE)

    def test_limit_precedes_catalog_and_page_graph_resolution(self):
        contents = make_indexed_pdf(MAX_STRUCTURE_OBJECTS + 1)
        # An invalid catalog reference would produce a different error if
        # the parser tried to resolve /Root before checking the object cap.
        contents = contents.replace(b"/Root 1 0 R", b"/Root 9999 0 R", 1)
        with self.assertRaises(PDFStructureParseError) as error:
            parse_pdf_structure(contents)
        self.assertEqual(str(error.exception), LIMIT_MESSAGE)

    def test_compressed_object_stream_entries_are_included(self):
        fixture = runpy.run_path(
            str(ROOT / "test-pdf-cross-reference-parsing.py")
        )["make_xref_stream_pdf"]
        content = fixture(object_stream=True)
        self.assertEqual(parse_pdf_structure(content), PDFStructure("1.5", 1))
        # Four ordinary xref entries plus one compressed page object.
        with patch("pdf_structure_parser.MAX_STRUCTURE_OBJECTS", 4):
            with self.assertRaises(PDFStructureParseError) as error:
                parse_pdf_structure(content)
            self.assertEqual(str(error.exception), LIMIT_MESSAGE)
        with patch("pdf_structure_parser.MAX_STRUCTURE_OBJECTS", 5):
            self.assertEqual(parse_pdf_structure(content), PDFStructure("1.5", 1))

    def test_existing_scanner_and_preferences_remain_unchanged(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        parser = (ROOT / "pdf_structure_parser.py").read_text(encoding="utf-8")
        self.assertIn("python3 test-pdf-object-limit.py -v", workflow)
        self.assertIn("total_objects += len(reader.xref_objStm)", parser)
        self.assertNotIn("pdf_structure_parser", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)


if __name__ == "__main__":
    unittest.main()
