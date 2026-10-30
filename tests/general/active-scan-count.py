#!/usr/bin/env python3
"""Keep the progress active-scan count truthful and separate from scan policy."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class ActiveScanCountTests(unittest.TestCase):
  def test_count_uses_confirmed_native_launches_not_pending_or_queued_requests(self):
    opener = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
    presentation = opener.split("private func showProgress() {", 1)[1].split(
      "private func startQueuedScans()", 1
    )[0]
    self.assertIn("activeScans: launchedScans.count)", presentation)
    self.assertNotIn("activeScans: pending.count", presentation)
    self.assertNotIn("activeScans: queued.count", presentation)
    self.assertNotIn("activeScans: running.count", presentation)
    self.assertIn("private var launchedScans = Set<String>()", opener)
    self.assertIn("self.launchedScans.insert(path)", opener)
    self.assertIn("self.launchedScans.remove(path)", opener)
    self.assertIn("launchedScans.removeAll()", opener)
    self.assertIn("guard ScanProgressPreference.isEnabled() else {", presentation)
    self.assertIn("panel?.orderOut(nil)", presentation)

  def test_accessible_label_is_presentation_only(self):
    panel = (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8")
    self.assertIn('activeScansLabel = NSTextField(labelWithString: "Active scans: 0")', panel)
    self.assertIn('activeScansLabel.setAccessibilityIdentifier("activeScanCount")', panel)
    self.assertIn('activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)', panel)
    self.assertIn("activeScansLabel.stringValue = \"Active scans: \\(count)\"", panel)
    self.assertIn("let count = max(0, activeScans)", panel)
    self.assertNotIn("Process()", panel)
    self.assertNotIn("scan-and-open.py", panel)
    self.assertNotIn("UserDefaults", panel)

  def test_required_ci_retains_native_integration_coverage(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    native = (ROOT / "test-native-cancellation.py").read_text(encoding="utf-8")
    component = (ROOT / "test-scan-progress-component.py").read_text(encoding="utf-8")
    self.assertIn("python3 test-active-scan-count.py -v", ci)
    self.assertIn("python3 test-native-cancellation.py", ci)
    self.assertIn("python3 test-scan-progress-component.py -v", ci)
    self.assertIn('progress.activeScansLabel.stringValue == "Active scans: 2"', native)
    for count in (0, 1, 2):
      self.assertIn(f'panel.activeScansLabel.stringValue == "Active scans: {count}"', component)


if __name__ == "__main__":
  unittest.main()
