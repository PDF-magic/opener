#!/usr/bin/env python3
"""Safe, in-memory regression fixtures for opener-0291."""
from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import unittest

from pypdf import PdfWriter
from pdf_incremental_revisions import (
    BLOCK_MESSAGE, MAX_PDF_BYTES, PDFIncrementalRevisionError,
    inspect_pdf_incremental_revisions,
)
from reference_pdf_collection import REFERENCE_PDFS


def append_revision(original, number=6, payload=b"<< /Marker (inert) >>"):
    previous = original.rsplit(b"startxref\n", 1)[1].splitlines()[0]
    data = bytearray(original)
    at = len(data)
    data.extend(str(number).encode() + b" 0 obj\n" + payload + b"\nendobj\n")
    next_xref = len(data)
    data.extend(b"xref\n" + str(number).encode() + b" 1\n")
    data.extend(f"{at:010d} 00000 n \n".encode())
    data.extend(b"trailer\n<< /Size 9 /Root 1 0 R /Prev " + previous + b" >>\n")
    data.extend(b"startxref\n" + str(next_xref).encode() + b"\n%%EOF\n")
    return bytes(data)


class IncrementalRevisionTests(unittest.TestCase):
    def setUp(self):
        self.base = REFERENCE_PDFS[0].content

    def test_reference_pdfs(self):
        for sample in REFERENCE_PDFS:
            with self.subTest(pdf=sample.identifier):
                report = inspect_pdf_incremental_revisions(sample.content)
                self.assertEqual(report.revision_count, 1)
                self.assertFalse(report.has_incremental_updates)
                self.assertEqual(report.updated_object_count, 0)
                self.assertEqual(report.added_object_count, 0)
                self.assertEqual(report.xref_formats, ("table",))
                self.assertIs(report.permits_open, False)

    def test_added_and_overwritten_objects(self):
        once = append_revision(self.base)
        twice = append_revision(
            once, number=3,
            payload=b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
        )
        report = inspect_pdf_incremental_revisions(twice)
        self.assertEqual(report.revision_count, 3)
        self.assertEqual(report.updated_object_count, 1)
        self.assertEqual(report.added_object_count, 1)
        self.assertEqual(report.xref_formats, ("table", "table", "table"))

    def test_pypdf_incremental_xref_stream(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        original = BytesIO()
        writer.write(original)
        incremental = PdfWriter(fileobj=BytesIO(original.getvalue()), incremental=True)
        incremental.add_metadata({"/Title": "inert update"})
        output = BytesIO()
        incremental.write(output)
        report = inspect_pdf_incremental_revisions(output.getvalue())
        self.assertEqual(report.revision_count, 2)
        self.assertEqual(report.xref_formats[-1], "stream")
        self.assertFalse(report.permits_open)

    def test_repeated_updates_count_once(self):
        payload = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"
        pdf = append_revision(append_revision(self.base, 3, payload), 3, payload)
        self.assertEqual(inspect_pdf_incremental_revisions(pdf).updated_object_count, 1)

    def test_invalid_prev_pointers(self):
        pdf = append_revision(self.base)
        pointer = b"/Prev " + self.base.rsplit(b"startxref\n", 1)[1].splitlines()[0]
        for corrupt in (pdf.replace(pointer, b"/Prev 99999999"),
                        pdf.replace(pointer, b"/Prev 0")):
            with self.assertRaises(PDFIncrementalRevisionError) as error:
                inspect_pdf_incremental_revisions(corrupt)
            self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_invalid_oversize_and_encrypted(self):
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("password")
        out = BytesIO()
        writer.write(out)
        for pdf in (None, b"", b"garbage", b"%PDF-1.7\ntruncated",
                    self.base[:-10], self.base + b"nonwhitespace",
                    out.getvalue(), b"%PDF" * (MAX_PDF_BYTES // 4 + 1)):
            with self.subTest(sample=str(type(pdf))):
                with self.assertRaises(PDFIncrementalRevisionError) as error:
                    inspect_pdf_incremental_revisions(pdf)
                self.assertEqual(str(error.exception), BLOCK_MESSAGE)

    def test_immutable_inert_findings(self):
        report = inspect_pdf_incremental_revisions(self.base)
        with self.assertRaises(FrozenInstanceError):
            report.revision_count = 9
        with self.assertRaises(FrozenInstanceError):
            report.permits_open = True
        self.assertNotIn(
            "inert", repr(inspect_pdf_incremental_revisions(append_revision(self.base)))
        )

    def test_scanner_and_preference_noninterference(self):
        scanner = (Path(__file__).resolve().parents[2] / "scan-and-open.py").read_text()
        self.assertNotIn("pdf_incremental_revisions", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_policy_definitions import PROTECTION_POLICIES, ProtectionProfileID
        self.assertFalse(PROTECTION_POLICIES[ProtectionProfileID.ENHANCED].selectable)


if __name__ == "__main__":
    unittest.main()
