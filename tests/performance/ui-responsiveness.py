#!/usr/bin/env python3
"""Portable benchmark contract and scanner-safety regressions."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("ui_response", ROOT / "ui_responsiveness_benchmark.py")
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


class UIResponsivenessContracts(unittest.TestCase):
  def valid(self, delays=None):
    return {
      "heartbeat_delays_ms": [0.3] * 49 + [2.5] if delays is None else delays,
      "cancel_dispatch_delay_ms": 3.2,
      "scan_active_at_cancel": True,
      "cancel_action_available": True
    }

  def test_reported_statistics(self):
    self.assertEqual(benchmark.percentile([9, 2, 3, 7], .95), 9)
    self.assertEqual(benchmark.percentile([9, 2, 3, 7], .5), 3)
    report = benchmark.aggregate([self.valid(), self.valid()])
    self.assertEqual(report["heartbeat_observations"], 100)
    self.assertEqual(report["heartbeat_median_delay_ms"], 0.3)
    self.assertEqual(report["heartbeat_p95_delay_ms"], 0.3)
    self.assertEqual(report["heartbeat_max_delay_ms"], 2.5)
    self.assertFalse(report["scanner_verdict_measured"])
    self.assertFalse(report["real_clamav_measured"])

  def test_invalid_or_incomplete_runs_rejected(self):
    for values in ([], [1] * 39, [-1] * 40, [float("inf")] * 40,
                   [float("nan")] * 40, [True] * 40, ["1"] * 40):
      with self.assertRaises(ValueError):
        benchmark.validate_sample(self.valid(values))
    for key in ("scan_active_at_cancel", "cancel_action_available"):
      item = self.valid()
      item[key] = False
      with self.assertRaises(ValueError):
        benchmark.validate_sample(item)
    with self.assertRaises(ValueError):
      benchmark.aggregate([])

  def test_isolated_native_handler_and_real_cancel_control(self):
    original = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
    driver = benchmark.driver_source(Path("/tmp/gate.py"),
                                     Path("/tmp/inert.pdf"), Path("/tmp/started"))
    self.assertIn('URL(fileURLWithPath: "/tmp/gate.py")', driver)
    self.assertIn("panel.cancelButton.performClick(nil)", driver)
    self.assertIn("heartbeatDelays.append(late)", driver)
    self.assertIn("activeScans: launchedScans.count)", driver)
    self.assertNotIn(benchmark.ENTRY_MARKER, driver)
    self.assertIn(benchmark.GATE_REFERENCE, original)
    self.assertIn("ScanProgressPreference.isEnabled()", original)
    self.assertIn("process.terminate()", original)
    self.assertEqual(original, (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8"))

  def test_no_production_scan_bypass_or_preference_writes(self):
    source = (ROOT / "ui_responsiveness_benchmark.py").read_text(encoding="utf-8")
    for required in ("start_new_session=True", "os.killpg(process.pid, signal.SIGKILL)",
                     "run_once(root, 0)", "process.returncode != 0"):
      self.assertIn(required, source)
    for prohibited in ("remove_quarantine", "launch_clean_file", "UserDefaults.standard.set"):
      self.assertNotIn(prohibited, source)
    self.assertNotIn("clamscan", benchmark.SWIFT_DRIVER.lower())


if __name__ == "__main__":
  unittest.main()
