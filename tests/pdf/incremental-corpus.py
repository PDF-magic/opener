#!/usr/bin/env python3
"""opener-1034: deterministic, harmless PDFs with real incremental updates."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import unittest

from pypdf import PdfReader

from pdf_incremental_revisions import (
    BLOCK_MESSAGE,
    PDFIncrementalRevisionError,
    inspect_pdf_incremental_revisions,
)
from reference_pdf_collection import (
    INCREMENTAL_REFERENCE_PDFS,
    REFERENCE_PDFS,
)


EXPECTED = {
    "incremental-added-metadata": (2, 1, 0, "/Helvetica", "Inert metadata revision"),
    "incremental-replaced-font": (2, 0, 1, "/Courier", None),
    "incremental-two-updates": (3, 1, 1, "/Courier", "Inert metadata revision"),
}


class IncrementalPDFCorpusTests(unittest.TestCase):
    def test_distinct_complete_documents_with_real_revision_chains(self):
        self.assertEqual(len(INCREMENTAL_REFERENCE_PDFS), len(EXPECTED))
        self.assertEqual({item.identifier for item in INCREMENTAL_REFERENCE_PDFS}, set(EXPECTED))
        self.assertEqual(len({sha256(item.content).digest() for item in INCREMENTAL_REFERENCE_PDFS}),
                         len(EXPECTED))
        for item in INCREMENTAL_REFERENCE_PDFS:
            with self.subTest(pdf=item.identifier):
                count = EXPECTED[item.identifier][0]
                self.assertEqual(item.simulated_scanner_outcome, "clean")
                self.assertTrue(item.content.startswith(b"%PDF-1.4\n"))
                self.assertTrue(item.content.endswith(b"%%EOF\n"))
                self.assertEqual(item.content.count(b"startxref\n"), count)
                self.assertEqual(item.content.count(b"%%EOF\n"), count)
                self.assertEqual(item.content.count(b"/Prev "), count - 1)
                xref = int(item.content.rsplit(b"startxref\n", 1)[1].splitlines()[0])
                self.assertEqual(item.content[xref:xref + 5], b"xref\n")

    def test_strict_reader_sees_current_objects_and_preserves_page_text(self):
        for item in INCREMENTAL_REFERENCE_PDFS:
            with self.subTest(pdf=item.identifier):
                _, _, _, font, title = EXPECTED[item.identifier]
                reader = PdfReader(BytesIO(item.content), strict=True)
                self.assertEqual(len(reader.pages), 1)
                self.assertEqual(reader.pages[0].extract_text().strip(), "Incremental reference")
                self.assertEqual(
                    str(reader.pages[0]["/Resources"]["/Font"]["/F1"].get_object()["/BaseFont"]),
                    font,
                )
                self.assertEqual(reader.metadata.title if reader.metadata else None, title)

    def test_inspector_reports_added_and_replaced_objects_without_authorizing_open(self):
        for item in INCREMENTAL_REFERENCE_PDFS:
            with self.subTest(pdf=item.identifier):
                count, added, replaced, _, _ = EXPECTED[item.identifier]
                report = inspect_pdf_incremental_revisions(item.content)
                self.assertEqual(report.revision_count, count)
                self.assertEqual(report.added_object_count, added)
                self.assertEqual(report.updated_object_count, replaced)
                self.assertEqual(report.xref_formats, ("table",) * count)
                self.assertTrue(report.has_incremental_updates)
                self.assertIs(report.permits_open, False)
                with self.assertRaises(FrozenInstanceError):
                    report.permits_open = True

    def test_corrupt_revision_history_fails_closed(self):
        for item in INCREMENTAL_REFERENCE_PDFS:
            with self.subTest(pdf=item.identifier):
                earlier_xref = int(item.content.split(b"startxref\n", 1)[1].splitlines()[0])
                pointer = b"/Prev " + str(earlier_xref).encode("ascii")
                self.assertIn(pointer, item.content)
                corrupted = item.content.replace(pointer, b"/Prev 99999999", 1)
                with self.assertRaises(PDFIncrementalRevisionError) as raised:
                    inspect_pdf_incremental_revisions(corrupted)
                self.assertEqual(str(raised.exception), BLOCK_MESSAGE)

    def test_baseline_corpus_and_scanner_remain_separate(self):
        self.assertEqual(len(REFERENCE_PDFS), 6)
        self.assertFalse({item.identifier for item in REFERENCE_PDFS}
                         & {item.identifier for item in INCREMENTAL_REFERENCE_PDFS})
        self.assertTrue(all(item.content.count(b"startxref\n") == 1
                            for item in REFERENCE_PDFS))
        scanner = (Path(__file__).resolve().parents[2] / "scan-and-open.py").read_text()
        self.assertNotIn("INCREMENTAL_REFERENCE_PDFS", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)


if __name__ == "__main__":
    unittest.main()
