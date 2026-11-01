#!/usr/bin/env python3
"""opener-1079: accurate and non-authorizing Maximum sanitization timings."""

import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import maximum_sanitization_benchmark as bench
import maximum_sanitized_copy as copies
from reference_pdf_collection import REFERENCE_PDFS

ROOT = Path(__file__).resolve().parents[2]


def verified_stub(source, output=b"%PDF-1.4\nsynthetic output"):
    return copies.SanitizerAttempt(copies.SanitizedCopyOffer(output, 1), None)


class MaximumSanitizationBenchmarkTests(unittest.TestCase):
    def test_workload_is_in_memory_and_identical_to_reviewed_reference(self):
        source = bench.fixture()
        self.assertEqual(source, REFERENCE_PDFS[0].content)
        self.assertLess(len(source), 4096)
        self.assertIn(b"(Clean baseline) Tj", source)
        self.assertNotIn(b"/OpenAction", source)
        self.assertNotIn(b"/JavaScript", source)

    def test_warmup_discarded_and_all_runs_use_identical_source(self):
        observed = []
        ticks = iter(i * 20_000_000 for i in range(8))

        def sanitizer(source):
            observed.append(source)
            return verified_stub(source)

        report = bench.benchmark(
            3, sanitizer=sanitizer, clock=lambda: next(ticks),
        )
        self.assertEqual(len(observed), 4)
        self.assertTrue(all(source is observed[0] for source in observed))
        self.assertEqual(report, {
            "schemaVersion": 1,
            "scope": "maximumRasterSanitizationOnly",
            "workload": "syntheticOnePageTextPdf",
            "inputBytes": len(observed[0]),
            "outputBytesMin": len(b"%PDF-1.4\nsynthetic output"),
            "outputBytesMax": len(b"%PDF-1.4\nsynthetic output"),
            "sampleCount": 3,
            "discardedWarmupRuns": 1,
            "medianMilliseconds": 20.0,
            "p90Milliseconds": 20.0,
        })
        self.assertNotIn("scanVerdict", report)
        self.assertNotIn("authorizesOpen", report)
        self.assertNotIn("Clean baseline", json.dumps(report))

    def test_all_failures_abort_without_partial_measurements_or_disclosure(self):
        for count in (0, 2, 11, True, 3.5):
            with self.subTest(count=count), self.assertRaises(ValueError):
                bench.benchmark(count)

        invalid = [
            None,
            copies._failed(copies.SanitizerFailureKind.UNAVAILABLE),
            copies._failed(copies.SanitizerFailureKind.TIMED_OUT),
            verified_stub(b"", output=b"%PDF-1.4\n" + bench.fixture()),
            verified_stub(b"", output=bench.fixture()),
        ]
        for result in invalid:
            with self.subTest(result=type(result).__name__):
                if (isinstance(result, copies.SanitizerAttempt) and
                        result.offer is not None and
                        result.offer.pdf_bytes != bench.fixture()):
                    continue
                with self.assertRaisesRegex(RuntimeError, "^Maximum sanitization benchmark failed"):
                    bench.benchmark(sanitizer=lambda _: result,
                                    clock=iter(range(12)).__next__)

        def private_failure(_):
            raise OSError("/Users/private/scan.pdf")

        with self.assertRaisesRegex(RuntimeError, "^Maximum sanitization benchmark failed") as caught:
            bench.benchmark(sanitizer=private_failure)
        self.assertNotIn("/Users/", str(caught.exception))

        def fail_after_warmup(_):
            if not hasattr(fail_after_warmup, "called"):
                fail_after_warmup.called = True
                return verified_stub(b"")
            raise RuntimeError("private PDF contents")

        with self.assertRaisesRegex(RuntimeError, "no measurements recorded"):
            bench.benchmark(sanitizer=fail_after_warmup)

        with self.assertRaisesRegex(RuntimeError, "no measurements recorded"):
            bench.benchmark(sanitizer=lambda _: verified_stub(b""),
                            clock=lambda: 123)

    def test_cli_rejects_invalid_sample_counts_without_json(self):
        run = subprocess.run(
            [sys.executable, str(ROOT / "maximum_sanitization_benchmark.py"),
             "--samples", "0"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(run.returncode, 0)
        self.assertEqual(run.stdout, "")
        self.assertIn("Choose 3 to 10", run.stderr)

    def test_live_scanner_and_unavailable_maximum_remain_untouched(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("maximum_sanitization_benchmark", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        from protection_profiles import ProtectionProfileID, PROTECTION_PROFILES
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        performance = json.loads(
            (ROOT / "PDFMagicOpenerApp/protection-performance.json").read_text()
        )
        self.assertEqual(performance["measurements"], [])
        workflow = (ROOT / ".github/workflows/consolidated-checks.yml").read_text()
        self.assertIn("python3 tests/maximum/sanitization-benchmark.py -v", workflow)
        self.assertIn("python3 maximum_sanitization_benchmark.py --samples 3", workflow)


if __name__ == "__main__":
    unittest.main()
