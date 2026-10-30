#!/usr/bin/env python3
"""opener-0375: clamd remains unconsidered until actual clamscan timing evidence."""
import importlib.util
import json
from pathlib import Path
from scanner_argument_validation import validated_file_size_options
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scanner_startup_benchmark",
                                               ROOT / "scanner_startup_benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scanner = self.root / "clamscan"
        self.scanner.write_text("#!/bin/sh\nexit 0\n")
        self.scanner.chmod(0o700)
        self.database = self.root / "signatures"
        self.database.mkdir()
        allowed = patch.object(benchmark, "TRUSTED_SCANNERS", (str(self.scanner),))
        allowed.start()
        self.addCleanup(allowed.stop)

    def test_requires_installed_explicit_trusted_scanner_and_database(self):
        for candidate in ("clamscan", "/usr/bin/env", "", str(self.root / "missing")):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                benchmark.measure(candidate, self.database)
        self.scanner.chmod(0o600)
        with self.assertRaises(ValueError):
            benchmark.measure(str(self.scanner), self.database)
        self.scanner.chmod(0o700)
        with self.assertRaises(ValueError):
            benchmark.measure(str(self.scanner), self.root / "missing-db")
        with self.assertRaises(ValueError):
            benchmark.measure(str(self.scanner), self.database, 4)
        with self.assertRaises(ValueError):
            benchmark.measure(str(self.scanner), self.database, cycles=2)

    def test_repeated_scans_are_timed_without_approving_or_opening(self):
        calls = []
        ticks = iter(range(101, 1000))
        def runner(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs, {
                "capture_output": True, "text": True,
                "timeout": 180, "check": False,
            })
            path = Path(args[-1])
            count = len(list(path.glob("fixture-*.pdf"))) if path.is_dir() else 1
            self.assertIn(count, (1, 5))
            return subprocess.CompletedProcess(args, 0, "\n".join(
                "fixture-%02d.pdf: OK" % i for i in range(count)
            ), "")
        report = benchmark.measure(str(self.scanner), self.database, runner=runner,
                                   clock=lambda: next(ticks))
        self.assertEqual(len(calls), 1 + 3 * (5 + 1))
        self.assertEqual(report["scope"], "syntheticClamscanStartupExperiment")
        self.assertIs(report["evidenceForClamdSwitch"], False)
        self.assertEqual(report["medianRepeatedOneShotMs"], 5000.0)
        self.assertEqual(report["medianOneProcessBatchMs"], 1000.0)
        self.assertEqual(report["medianExcessOneShotMs"], 4000.0)
        self.assertEqual(report["pairedCycles"], 3)
        self.assertEqual(report["fixtureCount"], 5)
        self.assertNotIn("authorizesOpen", report)
        self.assertNotIn(str(self.root), json.dumps(report))
        for args in calls:
            self.assertEqual(args[0], str(self.scanner))
            self.assertIn("--database=" + str(self.database), args)
            self.assertEqual(args[1:-1], benchmark.command(str(self.scanner), self.database, "x")[1:-1])
            self.assertNotIn("clamd", " ".join(args))
            self.assertTrue(Path(args[-1]).name.startswith(("fixture-", "clamscan-startup-")))

    def test_failed_warning_timeout_and_truncated_runs_publish_no_result(self):
        failures = (
            subprocess.CompletedProcess([], -9, "fixture: OK", ""),
            subprocess.CompletedProcess([], 0, "fixture: OK", "ClamAV Warning"),
            subprocess.CompletedProcess([], 0, "file: Empty file", ""),
            subprocess.CompletedProcess([], 0, "WARNING: OK", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 2, "", "private/file.pdf"),
        )
        for result in failures:
            with self.subTest(result=result), self.assertRaisesRegex(RuntimeError, "no results"):
                benchmark.measure(str(self.scanner), self.database,
                                  runner=lambda *args, **kwargs: result,
                                  clock=iter([1.0, 2.0]).__next__)
        with self.assertRaisesRegex(RuntimeError, "no results"):
            benchmark.measure(str(self.scanner), self.database,
                              runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                                  subprocess.TimeoutExpired("scanner", 180)),
                              clock=iter([1.0, 2.0]).__next__)

    def test_benchmark_is_not_loaded_by_live_scan_gate(self):
        live = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("scanner_startup_benchmark", live)
        self.assertNotIn("clamdscan", live)
        self.assertNotIn("clamd --", live)
        # Live size flags are now generated through the strict shared
        # validator, not embedded as string literals in scan-and-open.py.
        self.assertIn("size_options = validated_file_size_options(is_pdf=is_pdf)", live)
        for option in benchmark.command("/scanner", Path("/db"), Path("/fixture"))[1:-1]:
            if option.startswith(("--max-filesize=", "--max-scansize=")):
                self.assertIn(option, validated_file_size_options(is_pdf=True))
            else:
                self.assertIn(option if not option.startswith("--database=")
                              else "--database=", live)
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 scripts/run-test.py tests/scanner/startup-benchmark.py -v", ci)
        readme = (ROOT / "README.md").read_text()
        self.assertIn("scanner_startup_benchmark.py", readme)
        self.assertIn("no clamd migration", readme.lower())


if __name__ == "__main__":
    unittest.main()
