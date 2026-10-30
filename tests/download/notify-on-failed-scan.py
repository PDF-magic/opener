#!/usr/bin/env python3
"""Guard the isolated Notify on Failed Scan download notification option."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp/BrowsersSettingsView.swift"
PREF = ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift"


class FailedScanNotificationTests(unittest.TestCase):
  def test_accessible_toggle_is_explicit_and_not_an_active_scanner(self):
    source = VIEW.read_text()
    for expected in (
        'Toggle("Notify on Failed Scan", isOn: Binding(',
        'accessibilityIdentifier("notifyOnFailedDownloadScanToggle")',
        'accessibilityIdentifier("downloadFailureNotificationsSection")',
        "DownloadFailedScanNotificationPreference.save(enabled)",
        "DownloadFailedScanNotificationPreference.isEnabled()",
        "Required failure messages, blocked-opening alerts and security warnings remain visible",
        "Download scan notifications are not active",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)
    for forbidden in ("UserDefaults", "Process(", "NSWorkspace", "clamscan",
                      "permissions.request", "sendNativeMessage",
                      "downloads.open", "UNUserNotificationCenter"):
      self.assertNotIn(forbidden, source)
    names = re.findall(r'Toggle\("([^"]+)"', source)
    self.assertEqual(names.count("Notify on Failed Scan"), 1)
    self.assertIn("Show Only Warnings", names)
    self.assertIn("Enable Browser Download Monitoring", names)
    self.assertIn("Scan Other Supported Files", names)

  def test_safe_persistence_and_strict_failure_classification(self):
    source = PREF.read_text()
    section = source.split("enum DownloadScanNotificationOutcome {", 1)[1].split(
        "// Download scan-result presentation only.", 1
    )[0]
    for expected in (
        'static let key = "notifyOnFailedScan"',
        "ScanProgressPreference.suiteName",
        "CFGetTypeID(raw) == CFBooleanGetTypeID() else { return false }",
        "defaults.set(enabled, forKey: key)",
        "defaults.removeObject(forKey: key)",
        "case .failed, .incomplete:",
        "return isEnabled(defaults: defaults)",
        "case .clean, .blocked, .cancelled, .unknown:",
        "return false",
    ):
      self.assertIn(expected, section)
    for forbidden in ("selectedProtectionProfile", "skipScan", "permissions.request",
                      "clamscan", "NSWorkspace", "scan-and-open", "signatureFreshnessBypass"):
      self.assertNotIn(forbidden, section)

  def test_existing_safety_gates_and_ci_coverage(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("tests/download/notify-on-failed-scan.py -v", ci)
    self.assertIn("test-notify-on-failed-scan.swift", ci)
    background = (ROOT / "extensions/webextension/src/background.js").read_text()
    self.assertTrue(background.strip().endswith("void 0;"))
    src = PREF.read_text()
    self.assertIn('static let key = "showBlockedFileNotifications"', src)
    self.assertIn('static let key = "showOnlyWarnings"', src)
    self.assertIn("case .securityWarning, .scanIncompleteOrFailed, .unknown:", src)


if __name__ == "__main__":
  unittest.main()
