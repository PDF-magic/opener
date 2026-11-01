#!/usr/bin/env python3
"""Portable contract and real subprocess tests for opt-in app launch timings."""

import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("app_launch_benchmark", ROOT / "app_launch_benchmark.py")
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class AppLaunchBenchmarkTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.app = Path(self.tmp.name) / "PDFMagicOpener.app"
    (self.app / "Contents/MacOS").mkdir(parents=True)
    (self.app / "Contents/Info.plist").write_bytes(plistlib.dumps({
      "CFBundleIdentifier": benchmark.BUNDLE_ID,
      "CFBundleExecutable": "PDFMagicOpener",
      "CFBundlePackageType": "APPL",
    }))
    self.executable = self.app / "Contents/MacOS/PDFMagicOpener"
    self.executable.write_text("#!/usr/bin/env python3\n"
                               "import os, time\n"
                               "fd = int(os.environ['PDFMAGIC_LAUNCH_BENCHMARK_FD'])\n"
                               "os.write(fd, b'1')\n"
                               "time.sleep(5)\n", encoding="utf-8")
    self.executable.chmod(0o700)

  def test_real_child_ready_signal(self):
    home = Path(self.tmp.name) / "home"
    temp = Path(self.tmp.name) / "tmp"
    home.mkdir()
    temp.mkdir()
    duration = benchmark.launch_once(self.executable, home, temp, timeout=2)
    self.assertGreater(duration, 0)
    self.assertLess(duration, 2)

  def test_incorrect_marker_fails_without_result(self):
    self.executable.write_text("#!/usr/bin/env python3\nimport os\n"
                               "os.write(int(os.environ['PDFMAGIC_LAUNCH_BENCHMARK_FD']), b'0')\n")
    home = Path(self.tmp.name) / "home"
    temp = Path(self.tmp.name) / "tmp"
    home.mkdir()
    temp.mkdir()
    with self.assertRaisesRegex(RuntimeError, "no results"):
      benchmark.launch_once(self.executable, home, temp, timeout=1)

  def test_measure_discards_warmup_and_reports_aggregate_only(self):
    durations = iter([99, .4, .1, .3])
    report = benchmark.measure(self.app, 3, platform="darwin",
                               run_attempt=lambda *_: next(durations))
    self.assertEqual(report["discardedWarmup"], 1)
    self.assertEqual(report["sampleCount"], 3)
    self.assertEqual(report["medianMs"], 300)
    self.assertEqual(report["p90Ms"], 400)
    self.assertNotIn(str(self.app), json.dumps(report))

  def test_invalid_counts_platform_app_and_early_exit_fail_closed(self):
    with self.assertRaises(ValueError):
      benchmark.measure(self.app, 2, platform="darwin")
    with self.assertRaises(ValueError):
      benchmark.measure(self.app, 11, platform="darwin")
    with self.assertRaises(ValueError):
      benchmark.measure(self.app, 3, platform="linux")
    with self.assertRaises(ValueError):
      benchmark.measure(self.app / "missing", 3, platform="darwin")
    with self.assertRaises(ValueError):
      benchmark.measure(self.app, True, platform="darwin")
    self.executable.write_text("#!/usr/bin/env python3\npass\n")
    home = Path(self.tmp.name) / "home"
    temp = Path(self.tmp.name) / "tmp"
    home.mkdir()
    temp.mkdir()
    with self.assertRaises(RuntimeError):
      benchmark.launch_once(self.executable, home, temp, timeout=1)

  def test_rejects_failure_or_nonfinite_timing_without_partial_json(self):
    for failed in (float("nan"), float("inf"), 0, -1):
      attempts = iter([.1, .2, failed, .3])
      with self.assertRaises(RuntimeError):
        benchmark.measure(self.app, 3, platform="darwin",
                          run_attempt=lambda *_: next(attempts))

  def test_rejects_document_handling_and_symlinked_bundle(self):
    info_path = self.app / "Contents/Info.plist"
    with info_path.open("rb") as stream:
      info = plistlib.load(stream)
    info["CFBundleDocumentTypes"] = [{"CFBundleTypeName": "PDF"}]
    info_path.write_bytes(plistlib.dumps(info))
    with self.assertRaises(ValueError):
      benchmark.validate_app(self.app)
    alias = Path(self.tmp.name) / "alias.app"
    alias.symlink_to(self.app)
    with self.assertRaises(ValueError):
      benchmark.validate_app(alias)

  def test_marker_is_debug_only_and_does_not_modify_scan_gate(self):
    source = (ROOT / "PDFMagicOpenerApp/PDFMagicOpenerApp.swift").read_text()
    self.assertIn("#if DEBUG", source)
    self.assertIn("LaunchBenchmarkMarker.markFirstViewAppearance()", source)
    self.assertIn("PDFMAGIC_LAUNCH_BENCHMARK_FD", source)
    self.assertNotIn("clamscan", source)


if __name__ == "__main__":
  unittest.main()
