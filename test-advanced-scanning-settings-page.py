#!/usr/bin/env python3
"""Verify the Advanced Scanning preferences destination is present and safe."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
NAV = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
PAGE = ROOT / "PDFMagicOpenerApp" / "AdvancedScanningSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class AdvancedScanningSettingsPageTests(unittest.TestCase):
  def test_sidebar_adds_separate_advanced_scanning_destination(self):
    nav = NAV.read_text(encoding="utf-8")
    self.assertIn("case advancedScanning", nav)
    self.assertIn('case .advancedScanning: return "Advanced Scanning"', nav)
    self.assertIn("case .advancedScanning:\n      AdvancedScanningSettingsView()", nav)
    self.assertIn("case .security:", nav)
    self.assertIn("case .general:", nav)
    self.assertIn("case .browsers:", nav)
    self.assertIn("List(MainPreferenceSection.allCases", nav)

  def test_page_describes_existing_scanner_without_unsafe_controls(self):
    page = PAGE.read_text(encoding="utf-8")
    for required in (
        "struct AdvancedScanningSettingsView: View",
        'Text("Advanced Scanning")',
        'Label("Malware scanning"',
        'Label("File readiness"',
        'Label("Scan results"',
        'accessibilityIdentifier("advancedScanningMalwareSection")',
        'accessibilityIdentifier("advancedScanningReadinessSection")',
        'accessibilityIdentifier("advancedScanningResultsSection")',
        'accessibilityIdentifier("advancedScanningSettingsPage")',
        "ClamAV",
        "remain unchanged",
    ):
      with self.subTest(required=required):
        self.assertIn(required, page)

    for forbidden in (
        "Toggle(", "Picker(", "Slider(", "@AppStorage", "UserDefaults",
        "FileHandle(", "Process(", "NSWorkspace", "createFile(", "write(to:",
        "clamscan(", "setDefault", "LSSetDefault", "target-app.txt",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, page)

  def test_restore_recommended_limits_is_confirmed_scoped_and_accessible(self):
    page = PAGE.read_text(encoding="utf-8")
    shared = (ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text(
        encoding="utf-8"
    )
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    self.assertEqual(page.count('Button("Restore Recommended Limits"'), 2)
    for required in (
        'accessibilityIdentifier("restoreRecommendedLimitsButton")',
        'accessibilityIdentifier("restoreRecommendedLimitsStatus")',
        'accessibilityIdentifier("recommendedScannerLimitsSection")',
        'isPresented: $showRestoreRecommendedLimitsConfirmation',
        'Button("Cancel", role: .cancel)',
        'RecommendedScannerLimitsReset.restore()',
        'case .restored:',
        'case .alreadyRecommended:',
        'case .unavailable:',
        "fixed safety limits",
        "no editable scanner-limit control",
        "all other saved preferences remain unchanged",
    ):
      with self.subTest(required=required):
        self.assertIn(required, page)
    self.assertIn('static let concurrencyOverrideKey = "maxConcurrentScans"', shared)
    self.assertIn('defaults.removeObject(forKey: concurrencyOverrideKey)', shared)
    self.assertIn('defaults.set(previous, forKey: concurrencyOverrideKey)', shared)
    for forbidden in ("removePersistentDomain", "setPersistentDomain", "clamscan",
                      "target-app.txt", "LSSetDefault", "Process("):
      self.assertNotIn(forbidden, shared.split("enum RecommendedScannerLimitsReset {", 1)[1])
    self.assertIn("test-recommended-scanner-limits.swift", ci)
    self.assertIn("test-advanced-scanning-settings-page.py -v", ci)

  def test_page_is_part_of_built_swiftui_app_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = AdvancedScanningSettingsView.swift;", project)
    self.assertIn("B18100000000000000000001", project)
    self.assertIn("B18100000000000000000002", project)


if __name__ == "__main__":
  unittest.main()
