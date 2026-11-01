#!/usr/bin/env python3
"""opener-1073: benchmark a small real text PDF without changing scan policy."""

import json
from pathlib import Path
import subprocess
import sys
import unittest

from pdf_structure_parser import PDFStructure
from reference_pdf_collection import REFERENCE_PDFS
import small_text_pdf_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[2]


class SmallTextPDFBenchmarkTests(unittest.TestCase):
    def test_fixture_is_a_bounded_reproducible_text_pdf(self):
        pdf = benchmark.fixture()
        self.assertEqual(pdf, REFERENCE_PDFS[0].content)
        self.assertLess(len(pdf), 4096)
        self.assertIn(b"(Clean baseline) Tj", pdf)
        self.assertNotIn(b"/OpenAction", pdf)
        self.assertNotIn(b"/JavaScript", pdf)

    def test_all_runs_use_identical_bytes_and_discard_warmup(self):
        observed = []
        ticks = iter(i * 20_000_000 for i in range(12))

        def analyzer(pdf):
            observed.append(pdf)
            return PDFStructure("1.4", 1)

        report = benchmark.benchmark(analyzer=analyzer,
                                     clock=lambda: next(ticks))
        self.assertEqual(len(observed), 6)
        self.assertTrue(all(pdf is observed[0] for pdf in observed))
        self.assertEqual(report, {
            "schemaVersion": 1,
            "scope": "timedPdfStructureAnalysisOnly",
            "fixture": "syntheticOnePageTextPdf",
            "fixtureBytes": len(observed[0]),
            "sampleCount": 5,
            "discardedWarmupRuns": 1,
            "medianMilliseconds": 20.0,
            "p90Milliseconds": 20.0,
        })
        self.assertNotIn("authorizesOpen", report)
        self.assertNotIn("scannerVerdict", report)

    def test_incomplete_failed_or_invalid_runs_publish_nothing(self):
        for samples in (0, 4, 21, True, 3.5):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                benchmark.benchmark(samples)
        for result in (None, object(), PDFStructure("1.4", 2),
                       PDFStructure("1.7", 1)):
            with self.subTest(result=result), self.assertRaisesRegex(
                    RuntimeError, "no measurements"):
                benchmark.benchmark(
                    analyzer=lambda pdf: result,
                    clock=iter(range(30)).__next__,
                )
        def failure(pdf):
            raise OSError("/Users/private/document.pdf")
        with self.assertRaisesRegex(RuntimeError, "^Small PDF benchmark failed"):
            benchmark.benchmark(analyzer=failure)
        with self.assertRaisesRegex(RuntimeError, "no measurements"):
            benchmark.benchmark(
                analyzer=lambda pdf: PDFStructure("1.4", 1),
                clock=lambda: 7,
            )

    def test_real_supervised_worker_and_cli_emit_labeled_measurement(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "small_text_pdf_benchmark.py"),
             "--samples", "5"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=180,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["scope"], "timedPdfStructureAnalysisOnly")
        self.assertEqual(report["sampleCount"], 5)
        self.assertGreater(report["medianMilliseconds"], 0)
        self.assertGreaterEqual(report["p90Milliseconds"], report["medianMilliseconds"])
        self.assertNotIn("Clean baseline", result.stdout)
        self.assertNotIn(str(ROOT), result.stdout)

    def test_live_opening_policy_and_measurement_ui_are_unchanged(self):
        live = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("small_text_pdf_benchmark", live)
        self.assertIn("if not cached_clean(cache_id):", live)
        report = (ROOT / "PDFMagicOpenerApp/protection-performance.json").read_text()
        self.assertEqual(json.loads(report)["measurements"], [])
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 tests/pdf/small-text-benchmark.py -v", ci)
        self.assertIn("python3 small_text_pdf_benchmark.py --samples 5", ci)
        self.assertTrue((ROOT / "docs/pdf/small-text-performance.md").is_file())


if __name__ == "__main__":
    unittest.main()
