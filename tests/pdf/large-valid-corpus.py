#!/usr/bin/env python3
"""opener-1041: large, complete, harmless PDF documents in the security corpus."""

from dataclasses import FrozenInstanceError
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader

from large_valid_pdf_corpus import (
    LARGE_PDF_MIN_BYTES, LARGE_VALID_PDF_CASES, build_large_valid_pdf,
)
from pdf_structure_parser import (
    MAX_STRUCTURE_INPUT_BYTES, PDFStructureFailureCode,
    PDFStructureParseFailure, parse_pdf_structure_result,
)
from reference_pdf_collection import REFERENCE_PDFS


ROOT = Path(__file__).resolve().parents[2]


class LargeValidPDFCorpusTests(unittest.TestCase):
    def test_large_documents_are_real_valid_pdfs_with_distinct_content_streams(self):
        self.assertEqual({case.identifier for case in LARGE_VALID_PDF_CASES},
                         {"single-large-stream", "many-large-pages"})
        self.assertEqual({case.page_count for case in LARGE_VALID_PDF_CASES},
                         {1, 256})
        self.assertEqual(len(REFERENCE_PDFS), 6)
        digests = set()
        with tempfile.TemporaryDirectory(prefix="large-valid-pdf-corpus-") as temporary:
            for case in LARGE_VALID_PDF_CASES:
                with self.subTest(document=case.identifier):
                    document = build_large_valid_pdf(case)
                    self.assertGreater(len(document), LARGE_PDF_MIN_BYTES)
                    self.assertTrue(document.startswith(b"%PDF-1.4\n"))
                    self.assertTrue(document.endswith(b"%%EOF\n"))
                    self.assertEqual(document.count(b"startxref\n"), 1)
                    self.assertEqual(document.count(b"%%EOF\n"), 1)
                    digest = sha256(document).digest()
                    self.assertNotIn(digest, digests)
                    digests.add(digest)
                    self.assertEqual(build_large_valid_pdf(case), document)

                    xref = int(document.rsplit(b"startxref\n", 1)[1].splitlines()[0])
                    entries = document[xref:].split(b"\n")
                    self.assertEqual(entries[0], b"xref")
                    object_count = 3 + 2 * case.page_count
                    self.assertEqual(entries[1], f"0 {object_count + 1}".encode())
                    for number in range(1, object_count + 1):
                        offset = int(entries[number + 2][:10])
                        self.assertTrue(document[offset:].startswith(
                            f"{number} 0 obj\n".encode("ascii")))

                    path = Path(temporary) / f"{case.identifier}.pdf"
                    path.write_bytes(document)
                    with path.open("rb") as stream:
                        reader = PdfReader(stream, strict=True)
                        self.assertFalse(reader.is_encrypted)
                        self.assertEqual(len(reader.pages), case.page_count)
                        for number in {0, case.page_count // 2, case.page_count - 1}:
                            page = reader.pages[number]
                            content = page.get_contents().get_data()
                            self.assertTrue(content.startswith(
                                f"BT /F1 12 Tf 72 720 Td (Large valid PDF page {number + 1}) Tj ET\n".encode()))
                            self.assertEqual(len(content),
                                             len(content.rstrip(b" ")) + case.padding_per_page)
                            self.assertEqual(page.mediabox.width, 612)
                        self.assertEqual(sha256(path.read_bytes()).digest(), digest)

    def test_large_valid_documents_are_not_auto_approved_by_bounded_inspection(self):
        self.assertEqual(MAX_STRUCTURE_INPUT_BYTES, LARGE_PDF_MIN_BYTES)
        for case in LARGE_VALID_PDF_CASES:
            with self.subTest(document=case.identifier):
                evidence = parse_pdf_structure_result(build_large_valid_pdf(case))
                self.assertIsInstance(evidence, PDFStructureParseFailure)
                self.assertIs(evidence.code, PDFStructureFailureCode.sizeLimit)
                self.assertIs(evidence.to_dict()["authorizesOpen"], False)

    def test_corpus_stays_separate_from_scanner_and_preferences(self):
        for case in LARGE_VALID_PDF_CASES:
            with self.assertRaises(FrozenInstanceError):
                case.page_count = 0
        with self.assertRaises(ValueError):
            build_large_valid_pdf(None)
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("large_valid_pdf_corpus", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("verify_file_integrity", scanner)
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/large-valid-corpus.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
