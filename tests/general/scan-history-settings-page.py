#!/usr/bin/env python3
"""Verify the optional Scan History preferences destination remains gated."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
PAGE = ROOT / "PDFMagicOpenerApp" / "ScanHistorySettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class ScanHistorySettingsPageTests(unittest.TestCase):
  def test_feature_is_off_by_default_and_not_a_fake_opt_in(self):
    main = MAIN.read_text(encoding="utf-8")
    self.assertIn("init(scanHistoryEnabled: Bool = false)", main)
    self.assertIn("self.scanHistoryEnabled = scanHistoryEnabled", main)
    self.assertIn("case scanHistory", main)
    self.assertIn('case .scanHistory: return "Scan History"', main)
    self.assertIn('case .scanHistory: return "clock.arrow.circlepath"', main)
    self.assertIn("if section != .scanHistory || scanHistoryEnabled {", main)
    self.assertRegex(main, r"case \.scanHistory:\s+ScanHistorySettingsView\(\)")
    self.assertNotIn("@AppStorage", main)
    self.assertNotIn("UserDefaults", main)

  def test_keyboard_navigation_skips_hidden_destination(self):
    main = MAIN.read_text(encoding="utf-8")
    self.assertIn("MainPreferenceSection.allCases.filter { $0 != .scanHistory || scanHistoryEnabled }", main)
    self.assertIn("visibleSections.firstIndex(of: selection ?? .general)", main)
    self.assertIn("let sections = visibleSections", main)
    self.assertIn("selectedIndex == visibleSections.count - 1", main)
    self.assertIn("guard sections.indices.contains(nextIndex) else { return }", main)
    self.assertIn("List(MainPreferenceSection.allCases, selection: $selection)", main)
    self.assertIn('accessibilityLabel("\\(section.title) settings")', main)
    self.assertIn('accessibilityHint("Show the \\(section.title) settings page")', main)

  def test_passive_page_has_accessible_content_and_no_data_operations(self):
    page = PAGE.read_text(encoding="utf-8")
    for required in (
      "struct ScanHistorySettingsView: View",
      'Text("Scan History")',
      'GroupBox("History availability")',
      'GroupBox("Privacy and protection")',
      'accessibilityIdentifier("scanHistoryAvailabilitySection")',
      'accessibilityIdentifier("scanHistoryPrivacySection")',
      'accessibilityIdentifier("scanHistorySettingsPage")',
      "explicitly enables it", "independently verify the user's opt-in",
      "does not automatically load, export, or delete document records",
      "PDF bytes, document text, attachments, browsing history, or source URLs",
      "not an authorization to open a document",
    ):
      with self.subTest(required=required):
        self.assertIn(required, page)
    self.assertEqual(page.count("Button("), 1)
    self.assertIn('Button("Show recent scan results")', page)
    self.assertIn("recentScanHistory = RecentScanHistoryReader.load()", page)
    self.assertNotIn(".onAppear", page)
    for forbidden in (
      "Toggle(", "Picker(", "@AppStorage", "UserDefaults",
      "FileManager", "FileHandle", "Process(", "NSWorkspace", "URLSession",
      "write(to:", "removeItem(", "clamscan(", "target-app.txt",
      "onAppear", "onOpenURL", "DocumentGroup",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, page)

  def test_xcode_target_compiles_page_and_ci_checks_it(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertEqual(project.count("path = ScanHistorySettingsView.swift;"), 1)
    self.assertIn("fileRef = B19900000000000000000002;", project)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
      "runOnlyForDeploymentPostprocessing", 1
    )[0]
    self.assertIn("B19900000000000000000001,", sources)
    ci = CI.read_text(encoding="utf-8")
    self.assertIn(
      "PYTHONPATH=. python3 tests/general/scan-history-settings-page.py -v", ci
    )
    self.assertIn("scanner-tests:", ci)
    self.assertIn("macos-build:", ci)


if __name__ == "__main__":
  unittest.main()
