#!/usr/bin/env python3
"""opener-1082: real isolated staging disk evidence and failure cleanup."""

from contextlib import redirect_stdout
from io import StringIO
import json
import subprocess
import unittest
from unittest.mock import patch

import maximum_temporary_output as staging
import temporary_disk_benchmark as benchmark


class TemporaryDiskBenchmarkTests(unittest.TestCase):
    def test_real_staging_reports_logical_and_allocated_bytes_and_releases(self):
        real = staging.stage_maximum_temporary_pdf
        created = []

        def record(pdf):
            lease = real(pdf)
            created.append(lease)
            return lease

        with patch.object(staging, "stage_maximum_temporary_pdf", side_effect=record), \
             patch.object(subprocess, "run", side_effect=AssertionError("scanner invoked")):
            report = benchmark.benchmark(64, 2, 2)
        self.assertEqual(report["scope"], "maximumTemporaryPdfStagingOnly")
        self.assertEqual(report["fixture"], "syntheticInertPdf")
        self.assertEqual(report["sampleCount"], 2)
        self.assertEqual(report["discardedWarmupRuns"], 1)
        self.assertEqual(report["copies"], 2)
        self.assertEqual(report["medianObservedPeakLogicalBytes"],
                         2 * report["inputBytes"])
        self.assertGreaterEqual(report["maxObservedPeakAllocatedBytes"], 0)
        self.assertEqual(report["maxPostReleaseAllocatedBytes"], 0)
        self.assertIs(report["authorizesOpen"], False)
        self.assertEqual(len(created), 6)
        self.assertTrue(all(lease.released and not lease.path.exists()
                            for lease in created))

    def test_bounded_sizes_and_single_or_multiple_outputs(self):
        small = benchmark.benchmark(64, 1, 1)
        large = benchmark.benchmark(1024, 4, 1)
        self.assertGreater(large["inputBytes"], small["inputBytes"])
        self.assertEqual(large["medianObservedPeakLogicalBytes"],
                         large["inputBytes"] * 4)

    def test_rejects_unbounded_boolean_and_invalid_inputs_before_staging(self):
        with patch.object(staging, "stage_maximum_temporary_pdf",
                          side_effect=AssertionError("must not stage")):
            for args in ((True, 2, 3), (1000, 2, 3), (0, 2, 3),
                         (64, False, 3), (64, 0, 3), (64, 5, 3),
                         (64, 2, True), (64, 2, 0), (64, 2, 6)):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    benchmark.benchmark(*args)

    def test_stage_failure_releases_earlier_outputs_without_leaking_paths(self):
        real = staging.stage_maximum_temporary_pdf
        created = []

        def fail_second(pdf):
            if created:
                raise OSError("private path must not leak")
            lease = real(pdf)
            created.append(lease)
            return lease

        with patch.object(staging, "stage_maximum_temporary_pdf",
                          side_effect=fail_second):
            with self.assertRaises(RuntimeError) as caught:
                benchmark.benchmark(64, 2, 1)
        self.assertEqual(str(caught.exception), benchmark.ERROR)
        self.assertTrue(created[0].released)
        self.assertFalse(created[0].path.exists())

    def test_stat_failure_discards_partial_results_and_releases(self):
        real = staging.stage_maximum_temporary_pdf
        created = []

        def record(pdf):
            lease = real(pdf)
            created.append(lease)
            return lease

        with patch.object(staging, "stage_maximum_temporary_pdf", side_effect=record), \
             patch.object(benchmark, "_usage", side_effect=OSError("secret")):
            with self.assertRaisesRegex(RuntimeError, "incomplete") as caught:
                benchmark.benchmark(64, 1, 1)
        self.assertNotIn("secret", str(caught.exception))
        self.assertTrue(all(lease.released and not lease.path.exists()
                            for lease in created))

    def test_cli_reports_json_only_after_completed_measurement(self):
        buffer = StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(benchmark.main(["--stream-kib", "64", "--copies", "1",
                                             "--runs", "1"]), 0)
        report = json.loads(buffer.getvalue())
        self.assertEqual(report["sampleCount"], 1)
        self.assertFalse(report["authorizesOpen"])
        with redirect_stdout(StringIO()):
            with self.assertRaises(SystemExit) as caught:
                benchmark.main(["--copies", "9"])
        self.assertEqual(caught.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
