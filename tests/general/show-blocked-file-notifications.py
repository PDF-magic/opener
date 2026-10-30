#!/usr/bin/env python3
"""Ensure blocked PDF notifications are opt-in and never replace scanner warnings."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class BlockedNotificationTests(unittest.TestCase):
  def test_setting_and_delivery_are_wired(self):
    general = (ROOT / "PDFMagicOpenerApp/GeneralSettingsView.swift").read_text()
    prefs = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    opener = (ROOT / "brave-pdf-opener.swift").read_text()
    self.assertIn('Toggle("Show Blocked File Notifications"', general)
    self.assertIn('accessibilityIdentifier("showBlockedFileNotificationsToggle")', general)
    self.assertIn('BlockedFileNotificationPreference.save(enabled)', general)
    self.assertIn('static let key = "showBlockedFileNotifications"', prefs)
    self.assertIn("return false", prefs.split("enum BlockedFileNotificationPreference", 1)[1])
    self.assertIn("enabled && failure != nil && !cancelled", prefs)
    self.assertIn("deliverBlockedFileNotification", opener)
    self.assertIn("if let failure = failure {", opener)
    self.assertIn("alert.runModal()", opener)
    notifier = opener.split("func deliverBlockedFileNotification",1)[1].split("// A request's arrival time",1)[0]
    for forbidden in ("lastPathComponent", "requestedPaths", "failure.localizedDescription"):
      self.assertNotIn(forbidden, notifier)

if __name__ == "__main__":
  unittest.main()
