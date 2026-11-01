#!/usr/bin/env python3
"""opener-1045: deterministic PDF documents stressing bounded parser traversal."""

from hashlib import sha256
from io import BytesIO
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from pdf_structure_parser import (
    MAX_STRUCTURE_INPUT_BYTES,
    MAX_STRUCTURE_OBJECTS,
    MAX_STRUCTURE_PAGES,
    MAX_STRUCTURE_RECURSION_DEPTH,
    PDFStructure,
    PDFStructureParseError,
    parse_pdf_structure,
)
from timed_pdf_structure_analysis import (
    ANALYSIS_TIMEOUT_SECONDS,
    BLOCK_MESSAGE,
    TimedPDFAnalysisError,
    parse_pdf_structure_timed,
)


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests/fixtures/pdf-security-corpus/parser-timeouts"
WIDE_PAGES = 1024
DEEP_LEVELS = 64
CYCLIC_LEVELS = 48
EXPECTED_NAMES = {
    "wide-page-tree.pdf",
    "deep-page-tree.pdf",
    "cyclic-page-tree.pdf",
}


def build_pdf(objects):
    """Rebuild plain-ASCII PDF objects with exact, strict xref byte positions."""
    document = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for number, obj in sorted(objects.items()):
        offsets[number] = len(document)
        document.extend(f"{number} 0 obj\n".encode("ascii"))
        document.extend(obj + b"\nendobj\n")
    startxref = len(document)
    document.extend(f"xref\n0 {max(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for number in range(1, max(objects) + 1):
        if number in offsets:
            document.extend(f"{offsets[number]:010d} 00000 n \n".encode("ascii"))
        else:
            document.extend(b"0000000000 65535 f \n")
    document.extend(
        f"trailer\n<< /Size {max(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{startxref}\n%%EOF\n".encode("ascii")
    )
    return bytes(document)


def wide_page_tree():
    pages = b" ".join(f"{number} 0 R".encode("ascii")
                      for number in range(3, WIDE_PAGES + 3))
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Count 1024 /Kids [" + pages + b"] >>",
    }
    for number in range(3, WIDE_PAGES + 3):
        objects[number] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] >>"
        )
    return build_pdf(objects)


def deep_page_tree(levels, *, cycle=False):
    objects = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    for level in range(levels):
        number = level + 2
        child = 2 if cycle and level == levels - 1 else number + 1
        parent = f"/Parent {number - 1} 0 R ".encode("ascii") if level else b""
        objects[number] = (
            b"<< /Type /Pages /Count 1 /Kids ["
            + f"{child} 0 R".encode("ascii") + b"] " + parent + b">>"
        )
    if not cycle:
        objects[levels + 2] = (
            f"<< /Type /Page /Parent {levels + 1} 0 R "
            f"/MediaBox [0 0 100 100] >>".encode("ascii")
        )
    return build_pdf(objects)


def fixtures():
    return {
        "wide-page-tree.pdf": wide_page_tree(),
        "deep-page-tree.pdf": deep_page_tree(DEEP_LEVELS),
        "cyclic-page-tree.pdf": deep_page_tree(CYCLIC_LEVELS, cycle=True),
    }


class ParserTimeoutCorpusTests(unittest.TestCase):
    def test_tracked_documents_are_complete_distinct_and_reproducible(self):
        expected = fixtures()
        self.assertEqual(set(expected), EXPECTED_NAMES)
        self.assertEqual({p.name for p in CORPUS.glob("*.pdf")}, EXPECTED_NAMES)
        self.assertEqual(len({sha256(data).digest() for data in expected.values()}), 3)
        self.assertEqual(WIDE_PAGES, MAX_STRUCTURE_PAGES)
        self.assertEqual(DEEP_LEVELS, MAX_STRUCTURE_RECURSION_DEPTH)
        for name, generated in expected.items():
            with self.subTest(name=name):
                contents = (CORPUS / name).read_bytes()
                self.assertEqual(contents, generated)
                self.assertLess(len(contents), MAX_STRUCTURE_INPUT_BYTES)
                self.assertTrue(contents.startswith(b"%PDF-1.4\n"))
                self.assertTrue(contents.endswith(b"%%EOF\n"))
                self.assertEqual(contents.count(b"startxref\n"), 1)
                xref = int(contents.rsplit(b"startxref\n", 1)[1].splitlines()[0])
                self.assertEqual(contents[xref:xref + 5], b"xref\n")
                for forbidden in (
                    b"/JavaScript", b"/Launch", b"/OpenAction",
                    b"/EmbeddedFiles", b"/AcroForm", b"/AA ",
                ):
                    self.assertNotIn(forbidden, contents)

    def test_high_fanout_and_deep_tree_are_real_valid_pdf_documents(self):
        expected_pages = {"wide-page-tree.pdf": WIDE_PAGES, "deep-page-tree.pdf": 1}
        for name, page_count in expected_pages.items():
            with self.subTest(name=name):
                contents = (CORPUS / name).read_bytes()
                reader = PdfReader(BytesIO(contents), strict=True)
                self.assertFalse(reader.is_encrypted)
                self.assertEqual(len(reader.pages), page_count)
                self.assertEqual(
                    parse_pdf_structure(contents), PDFStructure("1.4", page_count)
                )
        self.assertLess(WIDE_PAGES + 2, MAX_STRUCTURE_OBJECTS)

    def test_cyclic_tree_is_valid_pdf_syntax_but_blocked_before_flattening(self):
        contents = (CORPUS / "cyclic-page-tree.pdf").read_bytes()
        reader = PdfReader(BytesIO(contents), strict=True)
        self.assertEqual(str(reader.trailer["/Root"]["/Type"]), "/Catalog")
        # Never ask an unsupervised generic parser to flatten a cyclic /Kids tree.
        with self.assertRaises(PDFStructureParseError) as caught:
            parse_pdf_structure(contents)
        self.assertEqual(
            str(caught.exception),
            "PDF structure could not be verified; opening was stopped.",
        )

    def test_real_supervised_worker_bounds_each_corpus_document(self):
        for name, expected_count in (
            ("wide-page-tree.pdf", WIDE_PAGES),
            ("deep-page-tree.pdf", 1),
            ("cyclic-page-tree.pdf", None),
        ):
            with self.subTest(name=name):
                contents = (CORPUS / name).read_bytes()
                started = time.monotonic()
                if expected_count is None:
                    with self.assertRaises(TimedPDFAnalysisError) as caught:
                        parse_pdf_structure_timed(contents)
                    self.assertEqual(str(caught.exception), BLOCK_MESSAGE)
                else:
                    result = parse_pdf_structure_timed(contents)
                    self.assertEqual(result, PDFStructure("1.4", expected_count))
                    self.assertIs(result.to_dict()["authorizesOpen"], False)
                self.assertLess(
                    time.monotonic() - started, ANALYSIS_TIMEOUT_SECONDS + 15
                )

    def test_forced_deadline_fails_closed_for_each_real_fixture(self):
        # Deterministic timeout injection avoids a 30-second sleep in CI.
        for name in EXPECTED_NAMES:
            with self.subTest(name=name):
                contents = (CORPUS / name).read_bytes()
                with patch(
                    "timed_pdf_structure_analysis.run_limited_worker",
                    side_effect=TimeoutError("private fixture name"),
                ) as worker:
                    with self.assertRaises(TimedPDFAnalysisError) as caught:
                        parse_pdf_structure_timed(contents)
                self.assertEqual(str(caught.exception), BLOCK_MESSAGE)
                self.assertNotIn("private", str(caught.exception))
                self.assertEqual(worker.call_args.args[1], contents)
                self.assertEqual(
                    worker.call_args.kwargs["timeout_seconds"],
                    ANALYSIS_TIMEOUT_SECONDS,
                )

    def test_corpus_is_ci_registered_without_touching_scanner_or_preferences(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn(
            "PYTHONPATH=. python3 tests/pdf/parser-timeout-corpus.py -v", ci
        )
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        self.assertNotIn("parser-timeout-corpus", scanner)
        self.assertNotIn("parse_pdf_structure_timed", scanner)


if __name__ == "__main__":
    unittest.main()
