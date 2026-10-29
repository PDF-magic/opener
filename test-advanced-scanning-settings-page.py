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
        "Toggle(", "Button(", "Picker(", "Slider(", "@AppStorage", "UserDefaults",
        "FileHandle(", "Process(", "NSWorkspace", "createFile(", "write(to:",
        "clamscan(", "setDefault", "LSSetDefault", "target-app.txt",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, page)

  def test_resource_usage_warning_is_accessible_and_read_only(self):
    page = PAGE.read_text(encoding="utf-8")
    warning = page.split('Label("Unusually resource-intensive settings"', 1)[1]
    warning = warning.split('accessibilityIdentifier("advancedScanningResourceWarning")', 1)[0]
    for required in (
        "exclamationmark.triangle.fill",
        "file-size limits",
        "archive-depth limits",
        "scan timeouts",
        "CPU use",
        "memory pressure",
        "scanning time",
        "Review resource impact before raising",
        "Scanner limits are currently fixed",
        "informational warning",
        "cannot change scanning",
        "bypass a failed scan",
        "saved choices",
        'Label("Resource usage warning"',
    ):
      with self.subTest(required=required):
        self.assertIn(required, warning)
    self.assertIn('accessibilityIdentifier("advancedScanningResourceWarning")', page)
    self.assertIn("Advanced scanning controls are not configurable in this version.", page)
    self.assertLess(page.index("advancedScanningResultsSection"),
                    page.index("advancedScanningResourceWarning"))
    for forbidden in ("Toggle(", "Button(", "Picker(", "Slider(", "@AppStorage",
                      "UserDefaults", "Process(", "NSWorkspace", "write(to:"):
      self.assertNotIn(forbidden, warning)

  def test_resource_warning_regression_is_run_by_existing_ci(self):
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    self.assertIn("python3 test-advanced-scanning-settings-page.py -v", ci)
    self.assertIn("macos-build:", ci)

  def test_page_is_part_of_built_swiftui_app_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = AdvancedScanningSettingsView.swift;", project)
    self.assertIn("B18100000000000000000001", project)
    self.assertIn("B18100000000000000000002", project)


if __name__ == "__main__":
  unittest.main()
