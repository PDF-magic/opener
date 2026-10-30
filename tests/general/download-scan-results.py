#!/usr/bin/env python3
"""Guard the browser download scan-result presentation preference."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]

class DownloadScanResultsTests(unittest.TestCase):
  def test_browsers_page_exposes_persistent_accessible_toggle(self):
    page = (ROOT / "PDFMagicOpenerApp/BrowsersSettingsView.swift").read_text()
    for expected in (
        'GroupBox("Download scan results")',
        'Toggle("Show Scan Results", isOn: Binding(',
        'accessibilityIdentifier("showDownloadScanResultsToggle")',
        'accessibilityIdentifier("downloadScanResultsSection")',
        "DownloadScanResultsPreference.save(enabled)",
        "DownloadScanResultsPreference.isEnabled()",
        "Browser download scanning is not currently active",
        "malware warnings",
        "never disabled or hidden",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, page)
    for forbidden in ("UserDefaults", "clamscan", "sendNativeMessage",
                      "permissions.request", "downloads.open", "NSWorkspace"):
      self.assertNotIn(forbidden, page)

  def test_preference_is_presentation_only_and_preserves_missing_values(self):
    src = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    contract = src.split("enum DownloadScanResultPresentation {", 1)[1]
    for required in (
        'static let key = "showScanResults"',
        "ScanProgressPreference.suiteName",
        "guard let stored = defaults.object(forKey: key) else { return true }",
        "CFGetTypeID(value) == CFBooleanGetTypeID() else { return true }",
        "defaults.set(enabled, forKey: key)",
        "if let previous { defaults.set(previous, forKey: key) }",
        "case .securityWarning: return true",
    ):
      self.assertIn(required, contract)
    for forbidden in ("clamscan", "launch", "scan-and-open", "permissions.request",
                      "selectedProtectionProfile", "removePersistentDomain"):
      self.assertNotIn(forbidden, contract)

  def test_integrations_and_native_safety_are_unchanged(self):
    shared = (ROOT / "extensions/webextension/manifest.json").read_text()
    background = (ROOT / "extensions/webextension/src/background.js").read_text()
    self.assertIn('"optional_permissions": [', shared)
    self.assertNotIn('"downloads.open"', shared)
    self.assertTrue(background.strip().endswith("void 0;"))
    scanner = (ROOT / "scan-and-open.py").read_text()
    self.assertIn("ClamAV", scanner)

if __name__ == "__main__":
  unittest.main()
