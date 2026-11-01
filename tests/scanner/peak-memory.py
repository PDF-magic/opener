#!/usr/bin/env python3
"""opener-1081: actual child peak RSS, without touching the production scanner."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import peak_memory_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[2]


class PeakMemoryBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scanner = self.root / "clamscan"
        self.scanner.write_text(
            '#!/bin/sh\nfor last; do :; done\nprintf "%s: OK\\n" "$last"\n'
        )
        self.scanner.chmod(0o700)
        self.database = self.root / "signatures"
        self.database.mkdir()
        allowed = patch.object(benchmark, "TRUSTED_SCANNERS", (str(self.scanner),))
        allowed.start()
        self.addCleanup(allowed.stop)

    def test_wait4_unit_conversion_is_platform_correct(self):
        self.assertEqual(benchmark.rss_mib(2048, "linux"), 2.0)
        self.assertEqual(benchmark.rss_mib(2 * 1024 * 1024, "darwin"), 2.0)
        for peak in (0, -1, float("nan"), float("inf"), True):
            with self.subTest(peak=peak), self.assertRaises(ValueError):
                benchmark.rss_mib(peak, "linux")
        with self.assertRaises(ValueError):
            benchmark.rss_mib(1024, "win32")

    def test_measurement_discards_warmup_and_returns_completed_peak_only(self):
        peaks = iter((500, 14, 20, 16))
        observed = []

        def sampler(scanner, database, fixture):
            observed.append((scanner, database, fixture.read_bytes()))
            return next(peaks)

        report = benchmark.measure(str(self.scanner), self.database, 3,
                                   sampler=sampler)
        self.assertEqual(len(observed), 4)
        self.assertEqual(report["medianPeakRssMiB"], 16)
        self.assertEqual(report["maxPeakRssMiB"], 20)
        self.assertEqual(report["sampleCount"], 3)
        self.assertEqual(report["discardedWarmupRuns"], 1)
        self.assertIs(report["authorizesOpen"], False)
        self.assertTrue(all(call[2] == observed[0][2] for call in observed))
        self.assertIn(b"(Clean baseline)", observed[0][2])
        for forbidden in (b"/OpenAction", b"/JavaScript", b"/Launch"):
            self.assertNotIn(forbidden, observed[0][2])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertEqual(report["measurement"], "directClamscanChildWait4MaxRSS")

    def test_exact_child_is_actually_measured_and_clamav_flags_preserved(self):
        if not hasattr(benchmark.os, "wait4"):
            self.skipTest("wait4 unavailable")
        result = benchmark.measure(str(self.scanner), self.database, 2)
        self.assertGreater(result["maxPeakRssMiB"], 0)
        self.assertGreater(result["medianPeakRssMiB"], 0)
        self.assertGreaterEqual(result["maxPeakRssMiB"], result["medianPeakRssMiB"])
        args = benchmark.command(str(self.scanner), self.database, Path("/fixture"))
        self.assertIn("--alert-exceeds-max=yes", args)
        self.assertIn("--alert-encrypted=yes", args)
        self.assertIn("--max-filesize=0", args)
        self.assertIn("--max-scansize=0", args)
        self.assertIn("--max-scantime=0", args)
        self.assertEqual(args[-2], "--")

    def test_bad_inputs_and_failed_samples_publish_nothing(self):
        for samples in (0, 11, True, 2.5):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                benchmark.measure(str(self.scanner), self.database, samples)
        with self.assertRaises(ValueError):
            benchmark.measure("/bin/sh", self.database)
        with self.assertRaises(ValueError):
            benchmark.measure(str(self.scanner), self.root / "missing")
        for result in (0, -3, float("nan"), float("inf"), None):
            with self.subTest(result=result), self.assertRaisesRegex(
                    RuntimeError, "no results"):
                benchmark.measure(str(self.scanner), self.database,
                                  sampler=lambda *_: result)
        with self.assertRaisesRegex(RuntimeError, "no results"):
            benchmark.measure(str(self.scanner), self.database,
                              sampler=lambda *_: (_ for _ in ()).throw(
                                  OSError("/private/secret.pdf")))

    def test_nonzero_and_timeout_are_fail_closed(self):
        self.scanner.write_text("#!/bin/sh\nexit 2\n")
        with self.assertRaisesRegex(RuntimeError, "no results"):
            benchmark.measure(str(self.scanner), self.database, 1)
        self.scanner.write_text("#!/bin/sh\nexec sleep 3\n")
        with patch.object(benchmark, "TIMEOUT_SECONDS", 0.04):
            with self.assertRaisesRegex(RuntimeError, "no results"):
                benchmark.measure(str(self.scanner), self.database, 1)

    def test_ci_and_live_opening_are_isolated(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/scanner/peak-memory.py -v", ci)
        self.assertIn("python3 peak_memory_benchmark.py", ci)
        self.assertIn("--scanner /usr/bin/clamscan --database", ci)
        self.assertTrue((ROOT / "docs/peak-memory-benchmark.md").is_file())
        live = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("peak_memory_benchmark", live)
        self.assertNotIn("peak_memory_benchmark", (ROOT / "scanner_startup_benchmark.py").read_text())
        self.assertEqual(json.loads((ROOT / "PDFMagicOpenerApp/protection-performance.json").read_text())["measurements"], [])


if __name__ == "__main__":
    unittest.main()
