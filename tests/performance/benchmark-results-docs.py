#!/usr/bin/env python3
"""Protect the documented benchmark snapshot from missing or fake evidence."""

from pathlib import Path
import runpy
import unittest

ROOT = Path(__file__).resolve().parents[2]
module = runpy.run_path(str(ROOT / "scripts" / "check-benchmark-results-docs.py"))


class BenchmarkResultsDocsTests(unittest.TestCase):
  def setUp(self):
    self.document = module["REPORT"].read_text(encoding="utf-8")
    self.validate = module["validate"]

  def test_current_document_has_complete_source_rows(self):
    self.assertEqual(self.validate(self.document), [])
    self.assertEqual(module["check"](), [])

  def test_missing_row_is_rejected(self):
    lines = [line for line in self.document.splitlines() if not line.startswith("| \x60small-text\x60")]
    self.assertTrue(self.validate("\n".join(lines)))

  def test_duplicate_row_is_rejected(self):
    row = next(line for line in self.document.splitlines() if line.startswith("| \x60medium-pdf\x60"))
    self.assertTrue(self.validate(self.document + "\n" + row + "\n"))

  def test_broken_evidence_link_is_rejected(self):
    changed = self.document.replace("https://github.com/PDF-magic/opener/actions/runs/", "https://example.invalid/run/", 1)
    self.assertTrue(self.validate(changed))

  def test_non_positive_measurements_are_rejected(self):
    changed = self.document.replace("78.670 ms median; 81.597 ms p90", "0 ms median; 0 ms p90")
    self.assertTrue(self.validate(changed))


if __name__ == "__main__":
  unittest.main()
