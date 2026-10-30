#!/usr/bin/env python3
"""opener-0464: unusual PDF object counts without changing scan authorization."""

import builtins
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, TextStringObject

from pdf_unusual_object_counts import (
    HIGH_OBJECT_COUNT, HIGH_OBJECTS_PER_PAGE, PDFUnusualObjectCountError,
    PDFUnusualObjectCounts, inspect_pdf_unusual_object_counts,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parent
_ERROR = "PDF object counts could not be fully inspected; opening was stopped."


def pdf_writer(pages=1, extras=0):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    for _ in range(extras):
        writer._add_object(DictionaryObject({
            NameObject("/Creator"): TextStringObject("harmless"),
        }))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def sparse_xref_pdf():
    """Valid classic xref subsections with one high-numbered indexed object."""
    data = bytearray(b"%PDF-1.4\n")
    offsets = {}
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
        900: b"<< /Producer (private-token) >>",
    }
    for number, content in objects.items():
        offsets[number] = len(data)
        data.extend(str(number).encode() + b" 0 obj\n" + content + b"\nendobj\n")
    startxref = len(data)
    # Explicitly mark every unoccupied object slot free; some strict parser
    # versions refuse sparse subsections without a complete free-entry table.
    data.extend(b"xref\n0 901\n0000000000 65535 f \n")
    for number in range(1, 901):
        if number in offsets:
            data.extend(f"{offsets[number]:010d} 00000 n \n".encode())
        else:
            data.extend(b"0000000000 00000 f \n")
    data.extend(
        b"trailer\n<< /Size 901 /Root 1 0 R >>\nstartxref\n"
        + str(startxref).encode() + b"\n%%EOF\n"
    )
    return bytes(data)


class PDFUnusualObjectCountTests(unittest.TestCase):
    def assert_rejected(self, contents):
        with self.assertRaises(PDFUnusualObjectCountError) as failure:
            inspect_pdf_unusual_object_counts(contents)
        self.assertEqual(str(failure.exception), _ERROR)
        self.assertNotIn("private", str(failure.exception))

    def test_reference_documents_are_bounded_non_authorizing_evidence(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                result = inspect_pdf_unusual_object_counts(sample.content)
                self.assertEqual(result.object_count, 5)
                self.assertEqual(result.page_count, 1)
                self.assertFalse(result.has_unusual_counts)
                self.assertEqual(result.anomaly_codes, ())
                self.assertFalse(result.permits_open)

    def test_ordinary_one_and_multiple_page_documents_not_flagged(self):
        for pages, extra in ((1, 0), (2, 5), (10, 50)):
            with self.subTest(pages=pages, extra=extra):
                result = inspect_pdf_unusual_object_counts(pdf_writer(pages, extra))
                self.assertEqual(result.page_count, pages)
                self.assertEqual(result.anomaly_codes, ())
                self.assertFalse(result.has_unusual_counts)

    def test_high_object_density_flagged_below_hard_absolute_limit(self):
        data = pdf_writer(1, HIGH_OBJECTS_PER_PAGE + 10)
        result = inspect_pdf_unusual_object_counts(data)
        self.assertGreater(result.object_count, HIGH_OBJECTS_PER_PAGE)
        self.assertLess(result.object_count, HIGH_OBJECT_COUNT)
        self.assertEqual(result.anomaly_codes, ("high_objects_per_page",))
        self.assertFalse(result.permits_open)

    def test_high_absolute_count_flagged_even_with_many_pages(self):
        data = pdf_writer(12, HIGH_OBJECT_COUNT)
        result = inspect_pdf_unusual_object_counts(data)
        self.assertGreaterEqual(result.object_count, HIGH_OBJECT_COUNT)
        self.assertEqual(result.anomaly_codes, ("high_object_count",))
        self.assertFalse(result.permits_open)

    def test_sparse_xref_numbering_is_signaled_not_reported_as_malware(self):
        result = inspect_pdf_unusual_object_counts(sparse_xref_pdf())
        self.assertEqual(result.object_count, 4)
        self.assertEqual(result.page_count, 1)
        self.assertEqual(result.highest_object_number, 900)
        self.assertEqual(result.anomaly_codes, ("sparse_object_ids",))
        self.assertFalse(result.permits_open)
        self.assertNotIn("private-token", str(result.to_dict()))

    def test_malformed_or_uninspectable_pdfs_fail_closed(self):
        encrypted = PdfWriter()
        encrypted.add_blank_page(width=100, height=100)
        encrypted.encrypt("unit-test-password")
        out = BytesIO()
        encrypted.write(out)
        for invalid in (
            None, "not PDF", b"not PDF", b"%PDF-1.4\n%%EOF\n",
            bytearray(pdf_writer()), out.getvalue(),
            b"x" * (16 * 1024 * 1024 + 1),
        ):
            with self.subTest(kind=type(invalid).__name__):
                self.assert_rejected(invalid)

    def test_missing_dependency_is_a_fixed_non_clean_result(self):
        imp = builtins.__import__

        def block(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("/private/pypdf-path")
            return imp(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=block):
            self.assert_rejected(REFERENCE_PDFS[0].content)

    def test_immutable_count_evidence_and_detached_serialization(self):
        obj = PDFUnusualObjectCounts(130, 1, 130, ("high_objects_per_page",))
        report = obj.to_dict()
        self.assertEqual(report["objectCount"], 130)
        self.assertEqual(report["anomalyCodes"], ["high_objects_per_page"])
        self.assertFalse(report["authorizesOpen"])
        report["anomalyCodes"].append("made_up")
        report["authorizesOpen"] = True
        self.assertEqual(obj.anomaly_codes, ("high_objects_per_page",))
        self.assertFalse(obj.to_dict()["authorizesOpen"])
        with self.assertRaises(FrozenInstanceError):
            obj.object_count = 1
        for args in (
            (True, 1, 1, ()),
            (0, 1, 1, ()),
            (1, 0, 1, ()),
            (1, 1, 0, ()),
            (1, 1, 1, ("unknown",)),
            (130, 1, 130, ()),
            (5, 1, 5, ["high_object_count"]),
        ):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    PDFUnusualObjectCounts(*args)
        with self.assertRaises(TypeError):
            PDFUnusualObjectCounts(1, 1, 1, (), True)

    def test_isolated_from_scanner_preferences_and_network(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        source = (ROOT / "pdf_unusual_object_counts.py").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertNotIn("pdf_unusual_object_counts", scanner)
        self.assertIn("test-pdf-unusual-object-counts.py -v", workflow)
        for forbidden in ("subprocess.", "requests.", "socket.", "write_text(",
                          "launch_clean_file(", "remove_quarantine(",
                          "os.environ", "eval(", "exec("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
