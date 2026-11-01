#!/usr/bin/env python3
"""opener-1075: bounded large PDF parsing measurements cannot approve opening."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import large_pdf_benchmark as benchmark
from large_valid_pdf_corpus import LARGE_PDF_MIN_BYTES, LARGE_VALID_PDF_CASES


ROOT = Path(__file__).resolve().parents[2]


class LargePDFBenchmarkTests(unittest.TestCase):
  def test_only_existing_inert_corpus_cases_and_bounded_runs(self):
    self.assertEqual(set(benchmark.CASE_NAMES),
                     {"single-large-stream", "many-large-pages"})
    self.assertEqual({case.page_count for case in LARGE_VALID_PDF_CASES}, {1, 256})
    for choice, runs in ((None, 1), ("missing.pdf", 1), ("all", 0),
                         ("all", 6), ("all", True), ("all", 1.5)):
      with self.subTest(choice=choice, runs=runs), self.assertRaises(ValueError):
        benchmark.validate(choice, runs)

  def test_benchmark_measures_real_large_pdf_and_all_content_streams(self):
    report = benchmark.measure("many-large-pages", 1)
    self.assertEqual(report["scope"], "syntheticLargePDFStrictParsing")
    self.assertIs(report["authorizes_open"], False)
    self.assertEqual(len(report["results"]), 1)
    result, = report["results"]
    self.assertEqual(result["case"], "many-large-pages")
    self.assertEqual(result["pages"], 256)
    self.assertGreater(result["input_bytes"], LARGE_PDF_MIN_BYTES)
    self.assertGreater(result["traversed_stream_bytes"], LARGE_PDF_MIN_BYTES)
    self.assertGreaterEqual(result["median_parse_and_traverse_ms"], 0)
    self.assertGreater(result["max_process_rss_mib"], 0)
    self.assertNotIn("authorizesOpen", json.dumps(result))
    self.assertNotIn("file_path", json.dumps(result))

  def test_failure_timeout_and_incomplete_samples_do_not_publish_results(self):
    sample = {
      "case": "single-large-stream", "pages": 1,
      "input_bytes": 18 * 1024 * 1024,
      "traversed_stream_bytes": 17 * 1024 * 1024,
      "parser": "pypdf", "parser_version": "6.21.3",
      "generate_ms": 1.0, "parse_and_traverse_ms": 2.0,
      "peak_process_rss_mib": 20.0,
    }
    invocations = []
    def successful(args, **kwargs):
      invocations.append((args, kwargs))
      return subprocess.CompletedProcess(args, 0, json.dumps(sample), "")
    report = benchmark.measure("single-large-stream", 2, runner=successful)
    self.assertEqual(report["results"][0]["runs"], 2)
    self.assertEqual(len(invocations), 2)
    for args, kwargs in invocations:
      self.assertEqual(args[1:], [str(ROOT / "large_pdf_benchmark.py"), "--worker",
                                  "--case", "single-large-stream", "--runs", "1"])
      self.assertEqual(kwargs, {"capture_output": True, "text": True,
                                "check": False, "timeout": 90})

    failures = (
      subprocess.CompletedProcess([], 1, "", "private/path"),
      subprocess.CompletedProcess([], 0, "bad json", ""),
      subprocess.CompletedProcess([], 0, json.dumps({**sample, "pages": 2}), ""),
      subprocess.CompletedProcess([], 0, json.dumps({**sample, "input_bytes": 10}), ""),
      subprocess.CompletedProcess([], 0, json.dumps(sample), "warning"),
    )
    for value in failures:
      with self.subTest(value=value), self.assertRaisesRegex(RuntimeError, "no results"):
        benchmark.measure("single-large-stream", 1,
                          runner=lambda *a, **k: value)
    with self.assertRaisesRegex(RuntimeError, "no results"):
      benchmark.measure("single-large-stream", 1,
                        runner=lambda *a, **k: (_ for _ in ()).throw(
                          subprocess.TimeoutExpired("worker", 90)))

  def test_benchmark_remains_separate_from_scan_gate_and_ci_runs_it(self):
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    self.assertNotIn("large_pdf_benchmark", scanner)
    self.assertIn("if not cached_clean(cache_id):", scanner)
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/pdf/large-pdf-benchmark.py -v", ci)
    self.assertIn("python3 large_pdf_benchmark.py --case many-large-pages --runs 1", ci)
    docs = (ROOT / "docs/pdf/large-pdf-benchmark.md").read_text(encoding="utf-8")
    for key in ("opener-1075", "parser", "ClamAV", "not", "16 MiB"):
      self.assertIn(key.lower(), docs.lower())


if __name__ == "__main__":
  unittest.main()
