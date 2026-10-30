#!/usr/bin/env python3
"""opener-0432: fail closed at a fixed PDF nesting and page-tree depth."""
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter

from pdf_structure_parser import (
    MAX_STRUCTURE_RECURSION_DEPTH,
    PDFStructure,
    PDFStructureParseError,
    parse_pdf_structure,
)

ROOT = Path(__file__).resolve().parent
ERROR = "PDF structure could not be verified; opening was stopped."


def make_pdf(*, levels=1, catalog_extra=b"", stream=None, cycle=False):
    """Build a one-page PDF with deterministic indirect page-tree references."""
    objects = {1: b"<< /Type /Catalog /Pages 2 0 R " + catalog_extra + b" >>"}
    for level in range(levels):
        number = level + 2
        child = 2 if cycle and level == levels - 1 else number + 1
        parent = (b"/Parent " + str(number - 1).encode("ascii") + b" 0 R "
                  if level else b"")
        objects[number] = (
            b"<< /Type /Pages /Count 1 /Kids ["
            + str(child).encode("ascii") + b" 0 R] " + parent + b">>"
        )
    leaf = levels + 2
    if not cycle:
        objects[leaf] = (
            b"<< /Type /Page /Parent " + str(leaf - 1).encode("ascii")
            + b" 0 R /MediaBox [0 0 100 100] >>"
        )
    if stream is not None:
        stream_number = leaf + 1
        objects[1] = (
            b"<< /Type /Catalog /Pages 2 0 R /Metadata "
            + str(stream_number).encode("ascii") + b" 0 R >>"
        )
        objects[stream_number] = (
            b"<< /Length " + str(len(stream)).encode("ascii")
            + b" >>\nstream\n" + stream + b"\nendstream"
        )

    document = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number, value in sorted(objects.items()):
        offsets[number] = len(document)
        document.extend(str(number).encode("ascii") + b" 0 obj\n"
                        + value + b"\nendobj\n")
    startxref = len(document)
    document.extend(b"xref\n0 " + str(max(objects) + 1).encode("ascii")
                    + b"\n0000000000 65535 f \n")
    for number in range(1, max(objects) + 1):
        if number in offsets:
            document.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
        else:
            document.extend(b"0000000000 65535 f \n")
    document.extend(
        b"trailer\n<< /Size " + str(max(objects) + 1).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n" + str(startxref).encode("ascii")
        + b"\n%%EOF\n"
    )
    return bytes(document)


class PDFRecursionDepthTests(unittest.TestCase):
    def assert_blocked(self, contents):
        with self.assertRaises(PDFStructureParseError) as result:
            parse_pdf_structure(contents)
        self.assertEqual(str(result.exception), ERROR)

    def test_page_tree_depth_exact_boundary_and_one_over(self):
        self.assertEqual(MAX_STRUCTURE_RECURSION_DEPTH, 64)
        for level in (1, 8, MAX_STRUCTURE_RECURSION_DEPTH):
            with self.subTest(depth=level):
                self.assertEqual(
                    parse_pdf_structure(make_pdf(levels=level)),
                    PDFStructure("1.4", 1),
                )
        self.assert_blocked(make_pdf(levels=MAX_STRUCTURE_RECURSION_DEPTH + 1))

    def test_deep_direct_arrays_rejected_before_parser_import(self):
        within = b"/Probe " + b"[" * 60 + b"0" + b"]" * 60
        self.assertEqual(
            parse_pdf_structure(make_pdf(catalog_extra=within)),
            PDFStructure("1.4", 1),
        )
        deeply_nested = make_pdf(catalog_extra=(
            b"/Probe " + b"[" * (MAX_STRUCTURE_RECURSION_DEPTH + 1)
            + b"0" + b"]" * (MAX_STRUCTURE_RECURSION_DEPTH + 1)
        ))
        with patch("builtins.__import__", side_effect=AssertionError("pypdf must not run")):
            self.assert_blocked(deeply_nested)

    def test_deep_mixed_direct_containers_are_rejected(self):
        opening = b"[<< /Nested "
        extra = b"/Probe " + opening * (MAX_STRUCTURE_RECURSION_DEPTH + 1)
        extra += b"0" + b">>]" * (MAX_STRUCTURE_RECURSION_DEPTH + 1)
        self.assert_blocked(make_pdf(catalog_extra=extra))

    def test_cyclic_page_tree_rejected_without_recursing(self):
        self.assert_blocked(make_pdf(levels=3, cycle=True))

    def test_comment_string_and_stream_data_do_not_count_as_object_recursion(self):
        extra = (b"/Lang (" + b"[" * 100 + b"\\(" + b">>" * 100
                 + b"\\)" + b") % " + b"[" * 100 + b"\n")
        self.assertEqual(
            parse_pdf_structure(make_pdf(catalog_extra=extra)),
            PDFStructure("1.4", 1),
        )
        self.assertEqual(
            parse_pdf_structure(make_pdf(stream=b"[" * 100 + b">>" * 100)),
            PDFStructure("1.4", 1),
        )
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        output = BytesIO()
        writer.write(output)
        self.assertEqual(parse_pdf_structure(output.getvalue()).page_count, 1)

    def test_parser_is_still_passive_and_ci_exercises_depth_guard(self):
        parser = (ROOT / "pdf_structure_parser.py").read_text(encoding="utf-8")
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("_validate_direct_nesting(contents)", parser)
        self.assertLess(parser.index("_validate_direct_nesting(contents)"),
                        parser.index("reader = PdfReader("))
        self.assertLess(parser.index("_validate_page_tree_depth(root)"),
                        parser.index("pages = reader.pages"))
        self.assertNotIn("pdf_structure_parser", gate)
        self.assertIn("python3 test-pdf-recursion-depth.py -v", workflow)
        self.assertIn("pip install --disable-pip-version-check -r requirements-enhanced-pdf.txt", workflow)


if __name__ == "__main__":
    unittest.main()
