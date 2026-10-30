#!/usr/bin/env python3
"""Verify the non-PDF browser download scope option remains opt-in and inert."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class ScanOtherSupportedFilesTests(unittest.TestCase):
  def test_visible_option_is_in_browsers_download_settings(self):
    view = (ROOT / "PDFMagicOpenerApp" / "BrowsersSettingsView.swift").read_text()
    for expected in (
        'GroupBox("Download scanning")',
        'Toggle("Scan Other Supported Files"',
        'accessibilityIdentifier("scanOtherSupportedFilesToggle")',
        'accessibilityIdentifier("downloadScanningSettingsSection")',
        'ScanOtherSupportedFilesPreference.isEnabled()',
        'ScanOtherSupportedFilesPreference.save(enabled)',
        'not currently connected',
        'does not enable download monitoring',
        'bypass safety checks',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, view)
    self.assertNotIn("clamscan", view)
    self.assertNotIn("sendNativeMessage", view)

  def test_persistent_opt_in_is_deny_by_default_and_scoped(self):
    prefs = (ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text()
    scope = prefs.split("enum ScanOtherSupportedFilesPreference {", 1)[1].split(
        "// The installed scanner currently has only one mandatory policy.", 1)[0]
    for required in (
        'static let key = "scanOtherSupportedFiles"',
        'ScanProgressPreference.suiteName',
        'CFGetTypeID(raw) == CFBooleanGetTypeID()',
        'else { return false }',
        'defaults.set(enabled, forKey: key)',
        'defaults.set(previous, forKey: key)',
        'defaults.removeObject(forKey: key)',
    ):
      with self.subTest(required=required):
        self.assertIn(required, scope)
    for forbidden in ("clamscan", "launch", "NSWorkspace", "setDefault",
                      "removePersistentDomain", "selectedProtectionProfile"):
      self.assertNotIn(forbidden, scope)

  def test_existing_pdf_only_native_handoff_stays_unmodified(self):
    native = (ROOT / "scan-and-open.py").read_text()
    handoff = (ROOT / "extensions/webextension/src/download-native-submit.js").read_text()
    defaults = (ROOT / "extensions/webextension/src/configuration-defaults.js").read_text()
    self.assertIn("Only regular files and application bundles can be scanned", native)
    self.assertIn("submitCompletedPdfDownloadToNative", handoff)
    self.assertIn("!pdfCandidate(id, path.localPath, mime)", handoff)
    self.assertIn("downloadMonitoringEnabled: false", defaults)
    self.assertIn("automaticScanRequestsEnabled: false", defaults)

  def test_ci_runs_ui_and_real_swift_persistence_checks(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 test-scan-other-supported-files.py -v", ci)
    self.assertIn(
        "PDFMagicOpenerApp/ScanProgressPreference.swift test-scan-other-supported-files.swift",
        ci,
    )
    self.assertIn("macos-build:", ci)


if __name__ == "__main__":
  unittest.main()
