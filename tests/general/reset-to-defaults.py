#!/usr/bin/env python3
"""Regression for the preferences-wide, confirmed Reset to Defaults action."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class ResetToDefaultsTests(unittest.TestCase):
  def test_action_requires_explicit_confirmation_and_reports_result(self):
    source = (ROOT / "PDFMagicOpenerApp/MainPreferencesView.swift").read_text()
    self.assertIn('Button("Reset to Defaults") {\n          showResetToDefaultsConfirmation = true', source)
    self.assertIn('accessibilityIdentifier("resetToDefaultsButton")', source)
    self.assertIn('isPresented: $showResetToDefaultsConfirmation', source)
    self.assertIn('Button("Reset to Defaults", role: .destructive)', source)
    self.assertIn('Button("Cancel", role: .cancel)', source)
    self.assertIn('if GeneralPreferencesReset.reset() {', source)
    self.assertIn('resetRevision += 1', source)
    self.assertIn('GeneralSettingsView()\n        .id(resetRevision)', source)
    self.assertIn('isPresented: $showResetToDefaultsResult', source)
    self.assertIn('Could not reset saved preferences', source)

  def test_reset_preserves_other_user_configuration_and_scanner_safety(self):
    source = (ROOT / "PDFMagicOpenerApp/MainPreferencesView.swift").read_text()
    self.assertIn("Your selected PDF browser", source)
    self.assertIn("scanner protections", source)
    for unsafe in ("UserDefaults(", "FileManager.", "LSSetDefault", "Process(",
                   "target-app.txt", "removePersistentDomain"):
      self.assertNotIn(unsafe, source)
    shared = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    reset = shared.split("enum GeneralPreferencesReset {", 1)[1].split(
      "// Create persisted presentation preferences", 1
    )[0]
    for key in ("ScanProgressPreference.key", "SuccessfulScanNotificationPreference.key",
                "BlockedFileNotificationPreference.key"):
      self.assertIn(key, reset)
    self.assertNotIn("removePersistentDomain", reset)

  def test_ci_retains_native_persistence_and_app_build_checks(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 scripts/run-test.py tests/general/reset-to-defaults.py -v", ci)
    self.assertIn("test-reset-general-preferences.swift", ci)
    self.assertIn("xcodebuild -project PDFMagicOpener.xcodeproj", ci)


if __name__ == "__main__":
  unittest.main()
