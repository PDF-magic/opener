#!/usr/bin/env python3
"""Contract and real-worker tests for opener-1078."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from types import SimpleNamespace

from pdf_structure_parser import PDFStructure
import enhanced_structure_benchmark as bench

ROOT = Path(__file__).resolve().parents[2]


class EnhancedStructureBenchmarkTests(unittest.TestCase):
    def test_fixed_inert_bounded_cases(self):
        self.assertEqual(bench.CASE_PAGES, {"one-page-text": 1, "thirty-two-pages": 32})
        first = bench.fixture("one-page-text")
        self.assertEqual(first, bench.fixture("one-page-text"))
        self.assertIn(b"(Clean baseline) Tj", first)
        for name in bench.CASE_PAGES:
            pdf = bench.fixture(name)
            self.assertLess(len(pdf), 16 * 1024 * 1024)
            self.assertTrue(pdf.startswith(b"%PDF-"))
            for forbidden in (b"/JavaScript", b"/OpenAction", b"/Launch"):
                self.assertNotIn(forbidden, pdf)
        with self.assertRaises(ValueError):
            bench.fixture("untrusted.pdf")

    def test_stage_timing_covers_callback_and_never_approves_open(self):
        observed = []
        def inspect(data):
            observed.append(data)
            return PDFStructure("1.4", 1)
        record = bench.measure_worker(
            "one-page-text", analyzer=inspect, clock=iter((10, 210)).__next__)
        self.assertEqual(record["elapsedNanoseconds"], 200)
        self.assertEqual(record["pages"], 1)
        self.assertEqual(record["stage"], "pdfStructure")
        self.assertEqual(record["outcome"], "completed")
        self.assertIs(record["authorizesOpen"], False)
        self.assertEqual(observed, [bench.fixture("one-page-text")])
        with self.assertRaises(RuntimeError):
            bench.measure_worker("one-page-text", analyzer=lambda data: PDFStructure("1.4", 2),
                                 clock=iter((10, 210)).__next__)

    def test_warmup_quantiles_and_fresh_worker_invocations(self):
        calls = []
        durations = iter((500_000_000, 1_000_000, 9_000_000, 2_000_000))
        def runner(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "case": "one-page-text", "pages": 1, "inputBytes": 600,
                "stage": "pdfStructure", "outcome": "completed",
                "elapsedNanoseconds": next(durations), "authorizesOpen": False,
            }))
        report = bench.benchmark("one-page-text", 3, runner=runner)
        self.assertEqual(report["scope"], "enhancedPdfStructureStageOnly")
        self.assertIs(report["authorizesOpen"], False)
        self.assertEqual(report["discardedWarmupRunsPerCase"], 1)
        self.assertEqual(report["results"][0]["medianMilliseconds"], 2)
        self.assertEqual(report["results"][0]["p90Milliseconds"], 9)
        self.assertEqual(len(calls), 4)
        for command, opts in calls:
            self.assertEqual(command[2:], ["--worker", "--case", "one-page-text"])
            self.assertEqual(opts["timeout"], bench.WORKER_TIMEOUT_SECONDS)
            self.assertFalse(opts["check"])

    def test_incomplete_runs_fail_without_reporting_partial_results(self):
        for bad in (0, 2, 11, True, 3.0):
            with self.subTest(samples=bad), self.assertRaises(ValueError):
                bench.benchmark(samples=bad)
        with self.assertRaises(ValueError):
            bench.benchmark("../../../private")
        def failed(command, **kwargs):
            return SimpleNamespace(returncode=1, stderr="/Users/private/file.pdf",
                                   stdout="")
        with self.assertRaisesRegex(RuntimeError, "^Enhanced structural benchmark failed"):
            bench.benchmark("one-page-text", 3, runner=failed)
        def false_approval(command, **kwargs):
            return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "case": "one-page-text", "pages": 1, "inputBytes": 600,
                "stage": "pdfStructure", "outcome": "completed",
                "elapsedNanoseconds": 100, "authorizesOpen": True,
            }))
        with self.assertRaisesRegex(RuntimeError, "no measurements recorded"):
            bench.benchmark("one-page-text", 3, runner=false_approval)

    def test_real_workers_benchmark_structure_only(self):
        completed = subprocess.run(
            [sys.executable, str(ROOT / "enhanced_structure_benchmark.py"),
             "--samples", "3"], cwd=ROOT, capture_output=True, text=True,
            check=True, timeout=120)
        report = json.loads(completed.stdout)
        self.assertEqual([r["case"] for r in report["results"]], list(bench.CASE_PAGES))
        self.assertEqual([r["pages"] for r in report["results"]], [1, 32])
        for result in report["results"]:
            self.assertEqual(result["samples"], 3)
            self.assertGreater(result["medianMilliseconds"], 0)
            self.assertGreaterEqual(result["p90Milliseconds"],
                                    result["medianMilliseconds"])
        self.assertFalse(report["authorizesOpen"])
        self.assertNotIn("Clean baseline", completed.stdout)
        self.assertNotIn(str(ROOT), completed.stdout)

    def test_no_production_scanner_or_preferences_changes(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("enhanced_structure_benchmark", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        timing = (ROOT / "enhanced_analysis_timing.py").read_text(encoding="utf-8")
        self.assertNotIn("enhanced_structure_benchmark", timing)
        self.assertTrue((ROOT / "docs/enhanced/structural-benchmark.md").is_file())
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/enhanced/structural-benchmark.py -v", ci)
        self.assertIn("python3 enhanced_structure_benchmark.py --samples 3", ci)


if __name__ == "__main__":
    unittest.main()
