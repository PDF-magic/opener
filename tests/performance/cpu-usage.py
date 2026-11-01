#!/usr/bin/env python3
"""opener-1083: isolate real ClamAV CPU accounting and fail-closed reporting."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import cpu_usage_benchmark as cpu

ROOT = Path(__file__).resolve().parents[2]


class CpuUsageBenchmarkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.scanner = self.folder / "clamscan"
        self.scanner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.scanner.chmod(0o700)
        self.database = self.folder / "database"
        self.database.mkdir()
        allow = patch.object(cpu, "TRUSTED_SCANNERS", (str(self.scanner),))
        allow.start()
        self.addCleanup(allow.stop)

    def fake_runner(self, args):
        path = args[-1]
        self.assertIn("--database=" + str(self.database), args)
        self.assertEqual(args[0], str(self.scanner))
        self.assertTrue(Path(path).read_bytes().startswith(b"%PDF-1.4\n"))
        return cpu.ProcessSample(0.015, 0.005, 0.04, 0, path + ": OK\n", "")

    def test_measures_cpu_of_successful_clamscan_children_not_wall_as_cpu(self):
        seen = []
        def runner(args):
            seen.append(args)
            return self.fake_runner(args)
        result = cpu.benchmark(str(self.scanner), self.database, 5, runner=runner)
        self.assertEqual(len(seen), 6)
        self.assertEqual(result["samples"], 5)
        self.assertEqual(result["discardedWarmups"], 1)
        self.assertEqual(result["medianUserCpuMs"], 15)
        self.assertEqual(result["medianSystemCpuMs"], 5)
        self.assertEqual(result["medianTotalCpuMs"], 20)
        self.assertEqual(result["p90TotalCpuMs"], 20)
        self.assertEqual(result["medianWallMs"], 40)
        self.assertEqual(result["medianCpuPercent"], 50)
        self.assertIs(result["authorizesOpen"], False)
        self.assertNotIn(str(self.folder), json.dumps(result))
        self.assertNotIn("stdout", result)

    def test_p90_uses_completed_samples_and_discards_warmup(self):
        ticks = iter([999, 10, 20, 30, 40])
        def runner(args):
            ms = next(ticks)
            return cpu.ProcessSample(ms / 1000, 0.0, ms / 1000,
                                     0, args[-1] + ": OK\n", "")
        result = cpu.benchmark(str(self.scanner), self.database, 4, runner=runner)
        self.assertEqual(result["medianTotalCpuMs"], 25)
        self.assertEqual(result["p90TotalCpuMs"], 40)

    def test_rejects_untrusted_executable_invalid_db_and_sample_counts(self):
        for scanner in ("clamscan", "/usr/bin/env", str(self.folder / "missing"), ""):
            with self.subTest(scanner=scanner), self.assertRaises(ValueError):
                cpu.benchmark(scanner, self.database, runner=self.fake_runner)
        for count in (0, 2, 8, True, 4.5, "5"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                cpu.benchmark(str(self.scanner), self.database, count,
                              runner=self.fake_runner)
        with self.assertRaises(ValueError):
            cpu.benchmark(str(self.scanner), self.folder / "missing-db")

    def test_no_result_after_failure_warning_mismatched_output_or_bad_cpu(self):
        invalid = (
            cpu.ProcessSample(0.1, 0, 0.1, 1, "", ""),
            cpu.ProcessSample(0.1, 0, 0.1, 0, "path: OK", ""),
            cpu.ProcessSample(0.1, 0, 0.1, 0, "file: OK\n", "WARNING"),
            cpu.ProcessSample(0, 0, 0.1, 0, "file: OK\n", ""),
            cpu.ProcessSample(float("nan"), 0, 0.1, 0, "file: OK\n", ""),
            cpu.ProcessSample(0.1, 0, 0, 0, "file: OK\n", ""),
            None,
        )
        for sample in invalid:
            with self.subTest(sample=sample), self.assertRaisesRegex(RuntimeError, "no measurements"):
                cpu.benchmark(str(self.scanner), self.database,
                              runner=lambda _: sample)
        calls = 0
        def late_failure(args):
            nonlocal calls
            calls += 1
            if calls == 4:
                raise subprocess.TimeoutExpired("clamscan", 1)
            return self.fake_runner(args)
        with self.assertRaises(RuntimeError):
            cpu.benchmark(str(self.scanner), self.database, runner=late_failure)
        self.assertEqual(calls, 4)

    @unittest.skipUnless(hasattr(__import__("os"), "wait4"), "Requires POSIX wait4")
    def test_wait4_collects_real_child_cpu_and_reaps_process(self):
        self.scanner.write_text(
            "#!/bin/sh\nfor arg do last=\"$arg\"; done\n"
            "printf '%s: OK\\n' \"$last\"\n", encoding="utf-8")
        self.scanner.chmod(0o700)
        record = cpu.run_clamscan([str(self.scanner), "/tmp/inert.pdf"])
        self.assertEqual(record.exit_code, 0)
        self.assertEqual(record.stdout, "/tmp/inert.pdf: OK\n")
        self.assertGreater(record.wall_seconds, 0)
        self.assertGreaterEqual(record.user_seconds, 0)
        self.assertGreaterEqual(record.system_seconds, 0)

    def test_disposable_ci_runs_real_clamscan_and_keeps_scan_gate_unchanged(self):
        workflow = (ROOT / ".github/workflows/cpu-usage-benchmark.yml").read_text()
        self.assertIn("python3 tests/performance/cpu-usage.py -v", workflow)
        self.assertIn("python3 cpu_usage_benchmark.py", workflow)
        self.assertIn("/usr/bin/clamscan", workflow)
        self.assertIn("benchmark-never-match", workflow)
        self.assertNotIn("cpu_usage_benchmark", (ROOT / "scan-and-open.py").read_text())
        self.assertIn("including signature database initialization",
                      (ROOT / "docs/performance/cpu-usage.md").read_text())


if __name__ == "__main__":
    unittest.main()
