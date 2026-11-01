#!/usr/bin/env python3
"""opener-1086: paired first-pass/repeat real scanner latency regressions."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cold_warm_scan_benchmark as perf

ROOT = Path(__file__).resolve().parents[2]


class ColdWarmTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.scanner = self.root / "clamscan"
        self.scanner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.scanner.chmod(0o700)
        self.db = self.root / "db"
        self.db.mkdir()
        allowed = patch.object(perf, "TRUSTED_SCANNERS", (str(self.scanner),))
        allowed.start()
        self.addCleanup(allowed.stop)

    def scan(self, args, **kwargs):
        self.assertEqual(kwargs, {"capture_output": True, "text": True,
                                  "timeout": 180, "check": False})
        self.assertEqual(args[:-1], perf.command(str(self.scanner), self.db, "x")[:-1])
        self.assertTrue(Path(args[-1]).read_bytes().startswith(b"%PDF-1.4\n"))
        return subprocess.CompletedProcess(args, 0, args[-1] + ": OK\n", "")

    def test_paired_first_repeat_measurements_and_median_delta(self):
        calls = []
        durations = [500, 500, 10, 8, 20, 12, 30, 18]
        timestamps = iter(t for duration in durations for t in (0, duration / 1000))
        def runner(args, **kwargs):
            calls.append(Path(args[-1]))
            return self.scan(args, **kwargs)
        report = perf.benchmark(str(self.scanner), self.db, pairs=3,
                                runner=runner, clock=lambda: next(timestamps))
        self.assertEqual(len(calls), 8)
        for i in range(0, 8, 2):
            self.assertEqual(calls[i], calls[i + 1])
        self.assertEqual(len(set(calls)), 4)
        self.assertEqual(report["medianColdMs"], 20)
        self.assertEqual(report["medianWarmMs"], 12)
        self.assertEqual(report["p90ColdMs"], 30)
        self.assertEqual(report["p90WarmMs"], 18)
        self.assertEqual(report["medianWarmMinusColdMs"], -8)
        self.assertAlmostEqual(report["medianColdToWarmRatio"], 1.667, places=3)
        self.assertEqual(report["discardedCalibrationPairs"], 1)
        self.assertFalse(report["clearsOsCaches"])
        self.assertFalse(report["persistsScannerEngine"])
        self.assertFalse(report["authorizesOpen"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("stdout", report)

    def test_faster_first_scan_is_reported_without_forcing_speedup(self):
        timestamps = iter(t for d in [1, 1, 1, 2, 1, 3, 1, 4]
                          for t in (0, d / 1000))
        result = perf.benchmark(str(self.scanner), self.db, pairs=3,
                                runner=self.scan, clock=lambda: next(timestamps))
        self.assertEqual(result["medianWarmMinusColdMs"], 2)
        self.assertLess(result["medianColdToWarmRatio"], 1)

    def test_rejects_untrusted_scanners_database_and_pair_counts(self):
        for scanner in ("clamscan", "/usr/bin/env", "", str(self.root / "missing")):
            with self.subTest(scanner=scanner), self.assertRaises(ValueError):
                perf.benchmark(scanner, self.db, runner=self.scan)
        self.scanner.chmod(0o600)
        with self.assertRaises(ValueError):
            perf.benchmark(str(self.scanner), self.db, runner=self.scan)
        self.scanner.chmod(0o700)
        with self.assertRaises(ValueError):
            perf.benchmark(str(self.scanner), self.root / "missing-db", runner=self.scan)
        for pairs in (0, 2, 8, True, 3.1, "3"):
            with self.subTest(pairs=pairs), self.assertRaises(ValueError):
                perf.benchmark(str(self.scanner), self.db, pairs, runner=self.scan)

    def test_fail_closed_on_bad_clean_output_warnings_and_timeouts(self):
        invalid = (
            subprocess.CompletedProcess([], 1, "", ""),
            subprocess.CompletedProcess([], 0, "file: OK\n", ""),
            subprocess.CompletedProcess([], 0, "file: OK\n", "Warning"),
            subprocess.CompletedProcess([], 0, "file: OK\nfile: OK\n", ""),
            subprocess.CompletedProcess([], 0, "", ""),
        )
        for sample in invalid:
            with self.subTest(sample=sample), self.assertRaisesRegex(RuntimeError, "no results"):
                perf.benchmark(str(self.scanner), self.db, 3,
                               runner=lambda *a, **kw: sample)
        with self.assertRaisesRegex(RuntimeError, "no results"):
            perf.benchmark(str(self.scanner), self.db, 3, runner=lambda *a, **kw:
                           (_ for _ in ()).throw(subprocess.TimeoutExpired("scanner", 180)))

    def test_late_failure_never_emits_partial_report(self):
        count = 0
        def runner(args, **kwargs):
            nonlocal count
            count += 1
            if count == 7:
                raise subprocess.TimeoutExpired("scanner", 180)
            return self.scan(args, **kwargs)
        with self.assertRaisesRegex(RuntimeError, "no results"):
            perf.benchmark(str(self.scanner), self.db, 3, runner=runner)
        self.assertEqual(count, 7)

    def test_invalid_clock_samples_are_rejected(self):
        for clock in (lambda: float("nan"), lambda: 1.0):
            with self.assertRaises(RuntimeError):
                perf.benchmark(str(self.scanner), self.db, 3,
                               runner=self.scan, clock=clock)

    def test_workflow_exercises_real_clamscan_and_live_gate_is_untouched(self):
        ci = (ROOT / ".github/workflows/cold-warm-scans.yml").read_text()
        self.assertIn("python3 tests/performance/cold-warm-scans.py -v", ci)
        self.assertIn("python3 cold_warm_scan_benchmark.py", ci)
        self.assertIn("/usr/bin/clamscan", ci)
        self.assertIn("benchmark-never-match", ci)
        self.assertNotIn("cold_warm_scan_benchmark", (ROOT / "scan-and-open.py").read_text())
        doc = (ROOT / "docs/performance/cold-warm-scans.md").read_text()
        self.assertIn("not a physically cold disk-cache", doc)


if __name__ == "__main__":
    unittest.main()
