#!/usr/bin/env python3
"""opener-1077: measure many embedded objects without changing the scan gate."""

from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import unittest

from pypdf import PdfReader
from pypdf.generic import IndirectObject
from pdf_embedded_object_sizes import PDFEmbeddedObjectSizes, inspect_pdf_embedded_object_sizes
import many_embedded_objects_benchmark as benchmark

ROOT = Path(__file__).resolve().parents[2]


class EmbeddedObjectsBenchmarkTests(unittest.TestCase):
  def test_fixture_is_deterministic_inert_and_within_enhanced_limits(self):
    pdf = benchmark.fixture()
    self.assertEqual(pdf, benchmark.fixture())
    self.assertLess(len(pdf), 16 * 1024 * 1024)
    self.assertTrue(pdf.startswith(b"%PDF-1.4\n"))
    for active in (b"/OpenAction", b"/JavaScript", b"/Launch", b"/AA"):
      self.assertNotIn(active, pdf)
    reader = PdfReader(BytesIO(pdf), strict=True)
    self.assertFalse(reader.is_encrypted)
    self.assertEqual(len(reader.pages), 1)
    self.assertEqual(len(reader.pages[0]["/Resources"]["/XObject"]), 256)
    self.assertEqual(len(reader.trailer["/Root"]["/Names"]["/EmbeddedFiles"]["/Names"]), 48)
    self.assertEqual(reader.get_object(IndirectObject(5, 0, reader)).get_data(), b"Z")
    evidence = inspect_pdf_embedded_object_sizes(pdf)
    self.assertEqual((evidence.stream_count, evidence.embedded_stream_count), (281, 24))
    self.assertFalse(evidence.has_large_objects)
    self.assertFalse(evidence.permits_open)

  def test_real_inspection_yields_complete_non_authorizing_measurements(self):
    report = benchmark.benchmark(3)
    self.assertEqual(report["scope"], "passiveEmbeddedObjectSizeInspectionOnly")
    self.assertEqual(report["imageXObjects"], 256)
    self.assertEqual(report["embeddedFiles"], 24)
    self.assertEqual(report["inspectedStreams"], 281)
    self.assertEqual(report["sampleCount"], 3)
    self.assertEqual(report["discardedWarmupRuns"], 1)
    self.assertIs(report["authorizesOpen"], False)
    self.assertGreater(report["medianMilliseconds"], 0)
    self.assertGreaterEqual(report["p90Milliseconds"], report["medianMilliseconds"])
    self.assertNotIn(str(ROOT), json.dumps(report))

  def test_warmup_same_bytes_and_exact_percentile(self):
    observed = []
    ticks = iter(n * 11_000_000 for n in range(8))
    def inspect(pdf):
      observed.append(pdf)
      return PDFEmbeddedObjectSizes(281, 24, 0, 0, 0, 0)
    report = benchmark.benchmark(3, inspector=inspect, clock=lambda: next(ticks))
    self.assertEqual(len(observed), 4)
    self.assertTrue(all(item is observed[0] for item in observed))
    self.assertEqual(report["medianMilliseconds"], 11.0)
    self.assertEqual(report["p90Milliseconds"], 11.0)

  def test_failed_incomplete_or_invalid_samples_never_emit_a_report(self):
    for samples in (0, 2, 11, True, 1.2):
      with self.subTest(samples=samples), self.assertRaises(ValueError):
        benchmark.benchmark(samples)
    for evidence in (None, object(), PDFEmbeddedObjectSizes(280, 24, 0, 0, 0, 0),
                     PDFEmbeddedObjectSizes(281, 23, 0, 0, 0, 0),
                     PDFEmbeddedObjectSizes(281, 24, 1, 0, 0, 0)):
      with self.subTest(evidence=evidence), self.assertRaisesRegex(RuntimeError, "no measurements"):
        benchmark.benchmark(3, inspector=lambda pdf: evidence,
                            clock=iter(range(8)).__next__)
    def fail(pdf):
      raise OSError("/private/document.pdf")
    with self.assertRaisesRegex(RuntimeError, "^Embedded-object benchmark failed") as cm:
      benchmark.benchmark(3, inspector=fail)
    self.assertNotIn("/private", str(cm.exception))
    with self.assertRaisesRegex(RuntimeError, "no measurements"):
      benchmark.benchmark(3,
                          inspector=lambda pdf: PDFEmbeddedObjectSizes(281, 24, 0, 0, 0, 0),
                          clock=lambda: 6)

  def test_cli_and_ci_are_opt_in_and_production_scan_gate_unchanged(self):
    completed = subprocess.run(
      [sys.executable, str(ROOT / "many_embedded_objects_benchmark.py"), "--samples", "3"],
      cwd=ROOT, capture_output=True, text=True, check=True, timeout=90,
    )
    report = json.loads(completed.stdout)
    self.assertIs(report["authorizesOpen"], False)
    self.assertNotIn(str(ROOT), completed.stdout)
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    self.assertNotIn("many_embedded_objects_benchmark", scanner)
    self.assertIn("if not cached_clean(cache_id):", scanner)
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/pdf/many-embedded-objects-benchmark.py -v", ci)
    self.assertIn("PYTHONPATH=. python3 many_embedded_objects_benchmark.py --samples 3", ci)
    self.assertTrue((ROOT / "docs/pdf/many-embedded-objects-benchmark.md").is_file())


if __name__ == "__main__":
  unittest.main()
