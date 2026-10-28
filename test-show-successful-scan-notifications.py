#!/usr/bin/env python3
"""Guard success notifications without changing the PDF scan gate or user settings."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PREF = (ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text()
GENERAL = (ROOT / "PDFMagicOpenerApp" / "GeneralSettingsView.swift").read_text()
OPENER = (ROOT / "brave-pdf-opener.swift").read_text()
INSTALLER = (ROOT / "install-allow-and-open.sh").read_text()
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()


class SuccessfulScanNotificationsTests(unittest.TestCase):
  def test_general_toggle_is_explicit_and_defaults_off(self):
    for token in (
      'Toggle("Show Successful Scan Notifications", isOn: Binding(',
      'get: { showSuccessfulScanNotifications }',
      'set: { updateSuccessfulScanNotificationPreference($0) }',
      'accessibilityIdentifier("showSuccessfulScanNotificationsToggle")',
      'accessibilityIdentifier("showSuccessfulScanNotificationsSection")',
      "SuccessfulScanNotificationPreference.isEnabled()",
      "SuccessfulScanNotificationPreference.save(enabled)",
      ".onAppear(perform: loadSuccessfulScanNotificationPreference)",
      "failure warnings remain unchanged",
    ):
      with self.subTest(token=token):
        self.assertIn(token, GENERAL)
    load = GENERAL.split("private func loadSuccessfulScanNotificationPreference()", 1)[1].split(
      "private func updateSuccessfulScanNotificationPreference", 1)[0]
    self.assertNotIn(".save(", load)
    self.assertIn('key = "showSuccessfulScanNotifications"', PREF)
    self.assertIn("static let suiteName = ScanProgressPreference.suiteName", PREF)
    self.assertIn("return false", PREF)
    self.assertIn("defaults.synchronize()", PREF)

  def test_success_notification_is_best_effort_and_path_free(self):
    for token in (
      "import UserNotifications",
      "UNUserNotificationCenter.current()",
      "center.getNotificationSettings",
      "center.requestAuthorization(options: [.alert])",
      "center.add(request)",
      "A PDF passed scanning and was handed off to your chosen application.",
      "SuccessfulScanNotificationPreference.shouldNotify(",
      "failure: failure, cancelled: cancelled",
      "self.cancelledRequests.contains(path)",
      "self.pendingSuccessNotifications += 1",
      "self.pendingSuccessNotifications -= 1",
      "if self.pending.isEmpty && self.pendingSuccessNotifications == 0",
    ):
      with self.subTest(token=token):
        self.assertIn(token, OPENER)
    notifier = OPENER.split("func deliverSuccessfulScanNotification(", 1)[1].split(
      "// A request's arrival time", 1)[0]
    for forbidden in ("requestedPaths", "lastPathComponent", "failure.localizedDescription",
                      "scanRequests", "NSAlert", "Process(", "FileManager"):
      self.assertNotIn(forbidden, notifier)
    self.assertIn("if let failure = failure {", OPENER)
    self.assertIn("alert.runModal()", OPENER)
    self.assertIn("process.terminationStatus != 0", OPENER)

  def test_normal_scan_and_existing_updater_stay_intact(self):
    self.assertIn("process.arguments = [script.path, path]", OPENER)
    self.assertIn("queued.append(path)", OPENER)
    self.assertIn("startQueuedScans()", OPENER)
    self.assertIn('ScanProgressPreference.isEnabled()', OPENER)
    self.assertIn('"$script_dir/PDFMagicOpenerApp/ScanProgressPreference.swift"', INSTALLER)
    for forbidden in ("clamscan", "target-app.txt", "LSSetDefault", "NSWorkspace", "Process("):
      self.assertNotIn(forbidden, PREF)

  def test_ci_covers_native_isolated_preference_and_scanner(self):
    self.assertIn("test-show-successful-scan-notifications.py -v", CI)
    self.assertIn("test-show-successful-scan-notifications.swift", CI)
    self.assertIn("brave-pdf-opener.swift scan-progress-view.swift PDFMagicOpenerApp/ScanProgressPreference.swift", CI)


if __name__ == "__main__":
  unittest.main()
