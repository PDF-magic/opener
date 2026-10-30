#!/usr/bin/env python3
"""Regression for confirmed reset limited to cosmetic General settings."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class GeneralResetTests(unittest.TestCase):
  def test_confirmation_is_required(self):
    page = (ROOT / "PDFMagicOpenerApp/GeneralSettingsView.swift").read_text()
    self.assertIn('Button("Reset General Preferences") {\n              showResetConfirmation = true', page)
    self.assertIn('.confirmationDialog(', page)
    self.assertIn('isPresented: $showResetConfirmation', page)
    self.assertIn('Button("Cancel", role: .cancel)', page)
    self.assertIn('Button("Reset General Preferences", role: .destructive)', page)
    self.assertIn('accessibilityIdentifier("resetGeneralPreferencesStatus")', page)
    self.assertIn('if GeneralPreferencesReset.reset() {', page)
    self.assertIn("loadBlockedFileNotificationPreference()", page)

  def test_reset_cannot_change_scanner_or_custom_browser(self):
    source = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    section = source.split("enum GeneralPreferencesReset {", 1)[1]
    self.assertIn("ScanProgressPreference.key", section)
    self.assertIn("SuccessfulScanNotificationPreference.key", section)
    self.assertIn("BlockedFileNotificationPreference.key", section)
    self.assertIn("defaults.removeObject(forKey: key)", section)
    self.assertNotIn("removePersistentDomain", section)
    for forbidden in ("preferredPDFBrowser", "LSSetDefault", "Process(", "scan-and-open",
                      "target-app.txt", "FileManager"):
      self.assertNotIn(forbidden, section)

  def test_ci_includes_native_and_structural_regressions(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 tests/general/reset-general-preferences.py -v", ci)
    self.assertIn("test-reset-general-preferences.swift", ci)


if __name__ == "__main__":
  unittest.main()
