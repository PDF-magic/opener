#!/usr/bin/env python3
"""Guard the user-controlled Show Only Warnings download display preference."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class ShowOnlyWarningsTests(unittest.TestCase):
  def test_accessible_toggle_is_explicit_and_non_scanning(self):
    source = (ROOT / "PDFMagicOpenerApp/BrowsersSettingsView.swift").read_text()
    for expected in (
        'Toggle("Show Only Warnings", isOn: Binding(',
        'accessibilityIdentifier("showOnlyDownloadWarningsToggle")',
        'accessibilityIdentifier("downloadWarningDisplaySection")',
        "DownloadWarningOnlyPreference.save(enabled)",
        "DownloadWarningOnlyPreference.isEnabled()",
        "Malware detections, scan failures, incomplete checks, blocked results",
        "This does not activate browser scanning",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)
    for forbidden in ("UserDefaults", "NSWorkspace", "Process(", "clamscan",
                      "sendNativeMessage", "downloads.open", "permissions.request"):
      self.assertNotIn(forbidden, source)

  def test_only_verified_nonwarnings_can_be_filtered(self):
    source = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    contract = source.split("enum DownloadWarningDisplayKind {", 1)[1].split(
        "// Only recognized optional scanner-limit override metadata is in scope.", 1
    )[0]
    for expected in (
        'static let key = "showOnlyWarnings"',
        "ScanProgressPreference.suiteName",
        "CFGetTypeID(value) == CFBooleanGetTypeID() else { return false }",
        "defaults.set(enabled, forKey: key)",
        "if let previous { defaults.set(previous, forKey: key) }",
        "case .verifiedCleanSummary, .verifiedInformationalSummary:",
        "return !isEnabled(defaults: defaults)",
        "case .securityWarning, .scanIncompleteOrFailed, .unknown:",
        "return true",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, contract)
    for forbidden in ("clamscan", "permissions.request", "launch(", "selectedProtectionProfile",
                      "removePersistentDomain", "quarantineDisabled", "signatureFreshnessBypass"):
      self.assertNotIn(forbidden, contract)

  def test_ci_runs_real_swift_persistence_regression(self):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("tests/download/show-only-warnings.py -v", workflow)
    self.assertIn("test-show-only-warnings.swift", workflow)
    self.assertIn("PDFMagicOpenerApp/ScanProgressPreference.swift test-show-only-warnings.swift", workflow)
    self.assertIn("xcrun swiftc -parse-as-library -warnings-as-errors", workflow)

  def test_existing_webextension_and_safety_gates_stay_inert(self):
    background = (ROOT / "extensions/webextension/src/background.js").read_text()
    manifest = (ROOT / "extensions/webextension/manifest.json").read_text()
    self.assertTrue(background.strip().endswith("void 0;"))
    self.assertIn('"optional_permissions": [', manifest)
    self.assertIn('"host_permissions": []', manifest)
    self.assertNotIn('"downloads.open"', manifest)


if __name__ == "__main__":
  unittest.main()
