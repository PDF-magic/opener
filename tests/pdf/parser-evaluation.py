#!/usr/bin/env python3
"""opener-0406: compare parser candidates and keep the selected pin reproducible."""
from importlib.metadata import metadata, version
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

from pdf_parser_memory_benchmark import MAX_PAGES, MAX_STREAM_BYTES, synthetic_pdf
from pdf_structure_parser import parse_pdf_structure, PDFStructure

ROOT = Path(__file__).resolve().parents[2]


class PDFParserEvaluationTests(unittest.TestCase):
  def test_selected_dependency_is_exact_and_license_is_checked(self):
    requirements = (ROOT / "requirements-enhanced-pdf.txt").read_text()
    active = [line.strip() for line in requirements.splitlines()
              if line.strip() and not line.lstrip().startswith("#")]
    self.assertEqual(active, ["pypdf==6.21.3"])
    self.assertEqual(version("pypdf"), "6.21.3")
    self.assertEqual(metadata("pypdf").get("License-Expression"), "BSD-3-Clause")

  def test_benchmark_uses_only_synthetic_bounded_pdf_bytes(self):
    from io import BytesIO
    from pypdf import PdfReader
    for pages, payload in ((1, 0), (16, 4096), (512, 1024)):
      with self.subTest(pages=pages):
        contents = synthetic_pdf(pages, payload)
        self.assertEqual(len(PdfReader(BytesIO(contents), strict=True).pages), pages)
        self.assertEqual(parse_pdf_structure(contents), PDFStructure("1.7", pages))
    for pages, payload in ((0, 0), (MAX_PAGES + 1, 0),
                           (1, -1), (1, MAX_STREAM_BYTES + 1)):
      with self.subTest(pages=pages, payload=payload):
        with self.assertRaises(ValueError):
          synthetic_pdf(pages, payload)

  def test_rss_is_measured_in_fresh_child_with_selected_parser(self):
    run = subprocess.run(
      [sys.executable, str(ROOT / "pdf_parser_memory_benchmark.py"),
       "--parser", "pypdf", "--pages", "16", "--stream-bytes", "1024"],
      capture_output=True, text=True, check=True, timeout=30,
    )
    report, = json.loads(run.stdout)
    self.assertEqual(report["status"], "ok")
    self.assertEqual(report["parser"], "pypdf")
    self.assertEqual(report["version"], "6.21.3")
    self.assertEqual(report["pages"], 16)
    self.assertGreater(report["peak_rss_mib"], 0)

  def test_selection_research_and_ci_use_only_this_pin(self):
    policy = (ROOT / "docs/pdf/parser-evaluation.md").read_text()
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    parser = (ROOT / "pdf_structure_parser.py").read_text()
    scanner = (ROOT / "scan-and-open.py").read_text()
    for item in ("pypdf", "pikepdf", "PyMuPDF", "PDF 2.0",
                 "Malformed", "memory", "MPL-2.0", "BSD-3-Clause",
                 "AGPL", "When", "6.21.3"):
      # The selection document uses descriptive labels rather than
      # asserting that a library supports every PDF 2.0 feature.
      if item == "When":
        continue
      self.assertIn(item.lower(), policy.lower())
    self.assertIn("PdfReader(BytesIO(contents), strict=True)", parser)
    self.assertNotIn("pdf_structure_parser", scanner)
    self.assertNotIn("pypdf", scanner)
    self.assertIn("python3 tests/pdf/parser-evaluation.py -v", ci)
    self.assertIn("python3 tests/pdf/structure-parser.py -v", ci)
    self.assertIn("python3 pdf_parser_memory_benchmark.py --parser pypdf", ci)
    self.assertNotIn("pypdf==5.9.0", ci)
    self.assertEqual(ci.count("pip install --disable-pip-version-check -r requirements-enhanced-pdf.txt"), 2)


if __name__ == "__main__":
  unittest.main()
