#!/usr/bin/env python3
"""Guard cross-process freshness without accessing live user configuration."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class CrossProcessConfigurationTests(unittest.TestCase):
  def test_shared_domain_is_refreshed_on_each_live_read(self):
    source = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    self.assertIn("struct EffectivePresentationConfiguration: Equatable", source)
    self.assertGreaterEqual(source.count("_ = defaults?.synchronize()"), 3)
    self.assertIn("ScanProgressPreference.isEnabled(defaults: defaults)", source)
    self.assertIn("SuccessfulScanNotificationPreference.isEnabled(defaults: defaults)", source)
    self.assertIn("BlockedFileNotificationPreference.isEnabled(defaults: defaults)", source)

  def test_ui_refreshes_on_reactivation_without_unverified_writes(self):
    source = (ROOT / "PDFMagicOpenerApp/GeneralSettingsView.swift").read_text()
    refresh = source.split("private func refreshEffectiveConfiguration()", 1)[1].split(
        "private func loadBrowserSelection()", 1)[0]
    self.assertIn("EffectivePresentationConfiguration.read()", refresh)
    self.assertNotIn(".save(", refresh)
    activated = source.split("for: NSApplication.didBecomeActiveNotification", 1)[1]
    for call in ("refreshEffectiveConfiguration()", "loadBrowserSelection()",
                 "refreshPDFHandlerStatus()"):
      self.assertIn(call, activated)
    self.assertNotIn("guard !loaded", source)
    self.assertIn("guard !savingBrowser else { return }", source)

  def test_native_handler_and_chooser_remain_authoritative(self):
    source = (ROOT / "brave-pdf-opener.swift").read_text()
    chooser = (ROOT / "PDFMagicOpenerApp/DefaultPDFBrowserPreferences.swift").read_text()
    self.assertIn("ScanProgressPreference.isEnabled()", source)
    self.assertIn("SuccessfulScanNotificationPreference.shouldNotify(", source)
    self.assertIn("BlockedFileNotificationPreference.notificationKind(", source)
    preferences = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    # The native handler now selects an exact malware vs generic blocked notice.
    # The classifier must still gate both outcomes through the saved opt-in.
    self.assertIn("guard shouldNotify(failure: failure, cancelled: cancelled, enabled: enabled)", preferences)
    self.assertIn('openat(parentFD, "target-app.txt", O_RDONLY | O_NOFOLLOW)', chooser)
    self.assertIn("saveVerified(_ option:", chooser)

if __name__ == "__main__":
  unittest.main()
