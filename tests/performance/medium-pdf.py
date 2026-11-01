#!/usr/bin/env python3
"""opener-1074: deterministic medium-PDF benchmark contract and safety."""

from io import BytesIO
from pathlib import Path
import unittest

from pypdf import PdfReader

from medium_pdf_benchmark import (
  MAX_MEDIUM_BYTES, MAX_RUNS, MEDIUM_PAGES, MIN_MEDIUM_BYTES,
  benchmark_medium_pdf, build_medium_pdf,
)
from pdf_structure_parser import PDFStructure, parse_pdf_structure

ROOT = Path(__file__).resolve().parents[2]


class MediumPDFBenchmarkTests(unittest.TestCase):
  def test_workload_is_medium_complete_and_inert(self):
    document = build_medium_pdf()
    self.assertGreaterEqual(len(document), MIN_MEDIUM_BYTES)
    self.assertLessEqual(len(document), MAX_MEDIUM_BYTES)
    self.assertEqual(document, build_medium_pdf())
    self.assertTrue(document.startswith(b"%PDF-1.7\n"))
    self.assertTrue(document.endswith(b"%%EOF\n"))
    reader = PdfReader(BytesIO(document), strict=True)
    self.assertFalse(reader.is_encrypted)
    self.assertEqual(len(reader.pages), MEDIUM_PAGES)
    self.assertEqual(parse_pdf_structure(document), PDFStructure("1.7", MEDIUM_PAGES))
    for disallowed in (b"/JavaScript", b"/OpenAction", b"/Launch", b"/EmbeddedFiles"):
      self.assertNotIn(disallowed, document)

  def test_measures_only_completed_samples_and_reports_correct_percentiles(self):
    durations = (5, 10, 20, 30, 40, 50)  # Warmup followed by five samples (ms).
    moments = iter(value for duration in durations for value in (0, duration * 1_000_000))
    seen = []

    def parse(document):
      seen.append(document)
      return PDFStructure("1.7", MEDIUM_PAGES)

    report = benchmark_medium_pdf(runs=5, parse=parse, clock_ns=lambda: next(moments))
    self.assertEqual(len(seen), 6)
    self.assertTrue(all(document is seen[0] for document in seen))
    self.assertEqual(report["warmups"], 1)
    self.assertEqual(report["runs"], 5)
    self.assertEqual(report["medianMs"], 30)
    self.assertEqual(report["p95Ms"], 50)
    self.assertEqual(report["stage"], "isolated-pdf-structure-analysis")
    self.assertFalse(report["authorizesOpen"])
    self.assertEqual(set(report), {"workload", "stage", "pages", "inputBytes",
                                    "warmups", "runs", "medianMs", "p95Ms",
                                    "authorizesOpen"})

  def test_invalid_counts_fail_before_parsing_and_bad_results_fail_closed(self):
    for runs in (0, MAX_RUNS + 1, True, 1.5, "3"):
      with self.subTest(runs=runs), self.assertRaises(ValueError):
        benchmark_medium_pdf(runs=runs, parse=lambda _: self.fail("Unexpected parse"))
    with self.assertRaises(RuntimeError):
      benchmark_medium_pdf(runs=1, parse=lambda _: PDFStructure("1.7", 1))
    with self.assertRaises(RuntimeError):
      benchmark_medium_pdf(runs=1, parse=lambda _: None)
    with self.assertRaises(RuntimeError):
      benchmark_medium_pdf(runs=1, parse=lambda _: PDFStructure("1.7", MEDIUM_PAGES),
                           clock_ns=lambda: 4)

  def test_benchmark_is_not_the_scanner_or_an_open_authorization(self):
    source = (ROOT / "medium_pdf_benchmark.py").read_text()
    scanner = (ROOT / "scan-and-open.py").read_text()
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    docs = (ROOT / "docs/performance/medium-pdf.md").read_text()
    self.assertNotIn("medium_pdf_benchmark", scanner)
    self.assertIn("if not cached_clean(cache_id):", scanner)
    self.assertIn("verify_file_integrity", scanner)
    self.assertNotIn("launch_clean_file", source)
    self.assertNotIn("remove_quarantine", source)
    self.assertIn("parse_pdf_structure_timed", source)
    self.assertIn("PYTHONPATH=. python3 tests/performance/medium-pdf.py -v", workflow)
    self.assertIn("python3 medium_pdf_benchmark.py --runs 3", workflow)
    self.assertIn("not end-to-end", docs)


if __name__ == "__main__":
  unittest.main()
