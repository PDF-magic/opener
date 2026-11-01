#!/usr/bin/env python3
"""opener-1076: synthetic image-based PDF benchmark safety and validity."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader

import scanned_pdf_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[2]


class ScannedImageBenchmarkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scanner = self.root / "clamscan"
        self.scanner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.scanner.chmod(0o700)
        self.database = self.root / "signatures"
        self.database.mkdir()
        allowed = patch.object(benchmark, "TRUSTED_SCANNERS", (str(self.scanner),))
        allowed.start()
        self.addCleanup(allowed.stop)

    def test_reproducible_pdf_is_scanned_raster_not_searchable_text(self):
        for pages in (1, 2, 4):
            with self.subTest(pages=pages):
                pdf = benchmark.scanned_pdf(pages)
                self.assertEqual(sha256(pdf).digest(),
                                 sha256(benchmark.scanned_pdf(pages)).digest())
                self.assertTrue(pdf.startswith(b"%PDF-1.4\n"))
                self.assertTrue(pdf.endswith(b"%%EOF\n"))
                self.assertLess(len(pdf), 8 * 1024 * 1024)
                reader = PdfReader(BytesIO(pdf), strict=True)
                self.assertEqual(len(reader.pages), pages)
                for page in reader.pages:
                    self.assertEqual(page.extract_text(), "")
                    images = page["/Resources"]["/XObject"]
                    self.assertEqual(list(images), ["/Scan"])
                    raster = images["/Scan"].get_object()
                    self.assertEqual(raster["/Subtype"], "/Image")
                    self.assertEqual(raster["/ColorSpace"], "/DeviceGray")
                    self.assertEqual(raster["/Filter"], "/FlateDecode")
                    self.assertEqual(len(raster.get_data()),
                                     benchmark.WIDTH * benchmark.HEIGHT)
                for active in (b"/JavaScript", b"/OpenAction", b"/Launch",
                               b"/EmbeddedFiles", b"/URI", b"/AA "):
                    self.assertNotIn(active, pdf)

    def test_strict_bounds_and_explicit_trusted_scanner(self):
        for pages in (0, 5, True, 2.5):
            with self.assertRaises(ValueError):
                benchmark.scanned_pdf(pages)
        for scanner in ("clamscan", "/usr/bin/env", str(self.root / "missing")):
            with self.assertRaises(ValueError):
                benchmark.measure(scanner, self.database)
        for pages, runs in ((0, 5), (5, 5), (2, 2), (2, 8)):
            with self.assertRaises(ValueError):
                benchmark.measure(str(self.scanner), self.database,
                                  pages=pages, runs=runs)
        with self.assertRaises(ValueError):
            benchmark.measure(str(self.scanner), self.root / "absent")
        self.scanner.chmod(0o600)
        with self.assertRaises(ValueError):
            benchmark.measure(str(self.scanner), self.database)

    def test_complete_real_command_timings_are_aggregated_not_verdicts(self):
        calls = []
        ticks = iter(range(10, 100))
        def runner(args, **kwargs):
            calls.append(args)
            self.assertEqual(kwargs, {
                "capture_output": True, "text": True,
                "timeout": benchmark.TIMEOUT_SECONDS, "check": False,
            })
            path = Path(args[-1])
            self.assertTrue(path.is_file())
            self.assertEqual(path.read_bytes(), benchmark.scanned_pdf(2))
            self.assertEqual(args, benchmark.command(str(self.scanner),
                                                     self.database, path))
            return subprocess.CompletedProcess(args, 0, f"{path}: OK\n", "")
        report = benchmark.measure(str(self.scanner), self.database, runner=runner,
                                   clock=lambda: next(ticks))
        self.assertEqual(len(calls), 6)  # warmup plus five real invocations
        self.assertEqual(report["sampleCount"], 5)
        self.assertEqual(report["scope"], "syntheticScannedPdfClamscanLatency")
        self.assertEqual(report["medianScanMs"], 1000.0)
        self.assertEqual(report["p90ScanMs"], 1000.0)
        self.assertIs(report["authorizesOpen"], False)
        self.assertEqual(report["rasterPixelsPerPage"], 1275 * 1650)
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("clamd", " ".join(" ".join(args) for args in calls))

    def test_no_results_for_timeout_warning_wrong_file_or_partial_scan(self):
        invalid = (
            subprocess.CompletedProcess([], -9, "", ""),
            subprocess.CompletedProcess([], 0, "something: OK\n", ""),
            subprocess.CompletedProcess([], 0, "", ""),
            subprocess.CompletedProcess([], 0, "path: OK", "ClamAV Warning"),
            subprocess.CompletedProcess([], 2, "error", ""),
        )
        for outcome in invalid:
            with self.subTest(outcome=outcome), self.assertRaisesRegex(
                    RuntimeError, "no results recorded"):
                benchmark.measure(str(self.scanner), self.database,
                                  runner=lambda *a, **k: outcome,
                                  clock=iter([1.0, 2.0]).__next__)
        with self.assertRaisesRegex(RuntimeError, "no results recorded"):
            benchmark.measure(str(self.scanner), self.database,
                              runner=lambda *a, **k: (_ for _ in ()).throw(
                                  subprocess.TimeoutExpired("clamscan", 180)),
                              clock=iter([1.0, 2.0]).__next__)
        with self.assertRaisesRegex(RuntimeError, "no results recorded"):
            benchmark.measure(str(self.scanner), self.database,
                              runner=lambda args, **kw: subprocess.CompletedProcess(
                                  args, 0, f"{args[-1]}: OK", ""),
                              clock=iter([2.0, 1.0]).__next__)

    def test_separate_from_live_scan_approval_and_wired_into_ci(self):
        production = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("scanned_pdf_benchmark", production)
        self.assertIn("verify_file_integrity", production)
        self.assertIn("if not cached_clean(cache_id):", production)
        ci = (ROOT / ".github/workflows/scanned-image-pdf-benchmark.yml").read_text(encoding="utf-8")
        self.assertIn("PYTHONPATH=. python3 tests/pdf/scanned-image-benchmark.py -v", ci)
        guide = (ROOT / "docs/scanned-image-pdf-benchmark.md").read_text(
            encoding="utf-8")
        self.assertIn("scan-process latency", guide)
        self.assertIn("not full PDF-opening latency", guide)


if __name__ == "__main__":
    unittest.main()
