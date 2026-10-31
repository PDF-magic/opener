#!/usr/bin/env python3
"""Ensure the standalone SwiftUI app exposes a real, safe main preferences window."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
VIEW = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class MainPreferencesWindowTests(unittest.TestCase):
  def test_window_uses_main_preferences_view_not_placeholder(self):
    app = APP.read_text(encoding="utf-8")
    self.assertIn("WindowGroup", app)
    self.assertIn("MainPreferencesView()", app)
    self.assertNotIn("Application settings will appear here.", app)
    self.assertNotIn("DocumentGroup", app)

  def test_sidebar_exposes_all_main_preferences_sections(self):
    view = VIEW.read_text(encoding="utf-8")
    for required in (
        "struct MainPreferencesView: View",
        "NavigationSplitView",
        "List(MainPreferenceSection.allCases",
        "case general", "case browsers", "case security",
        "GeneralSettingsView()",
        'BrowsersSettingsView()',
        'case .security: return "Protection"',
        'ProtectionSettingsView()',
        'case privacyAndLogs',
        'case .privacyAndLogs: return "Privacy and Logs"',
        'PrivacyAndLogsSettingsView()',
        'accessibilityIdentifier("mainPreferencesSidebar")',
    ):
      with self.subTest(required=required):
        self.assertIn(required, view)

  def test_protection_sidebar_routes_to_dedicated_page(self):
    main = VIEW.read_text(encoding="utf-8")
    self.assertIn("case security", main)
    self.assertIn('case .security: return "Protection"', main)
    self.assertRegex(main, r"case \.security:\s+ProtectionSettingsView\(\)")
    self.assertIn('accessibilityIdentifier("mainPreferencesSidebar")', main)

  def test_protection_page_describes_safeguards_without_changing_them(self):
    protection = (ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift").read_text(
        encoding="utf-8")
    for required in (
        "struct ProtectionSettingsView: View",
        'Text("Protection")',
        'GroupBox("Malware scanning")',
        'GroupBox("Unsafe or unverified files")',
        'GroupBox("Verified application handoff")',
        'accessibilityIdentifier("protectionSettingsPage")',
        'accessibilityIdentifier("malwareScanningSection")',
        'accessibilityIdentifier("unsafeFilesSection")',
        'accessibilityIdentifier("verifiedHandoffSection")',
    ):
      with self.subTest(required=required):
        self.assertIn(required, protection)
    for forbidden in (
        "Process(", "NSWorkspace", "FileHandle(", "UserDefaults",
        "onOpenURL", "DocumentGroup", "clamscan(", "LSSetDefault",
        "write(to:", "removeItem(", "setDefault", "target-app.txt",
        "Toggle(", "Picker(", "Slider(", "@AppStorage",
        "SelectedProtectionProfilePreference.save", "save(",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, protection)
    # Three intentional preview buttons are now present, but no scanner
    # preference write or policy activation is available from this page.
    self.assertIn("Button {", protection)
    self.assertIn("selectedPreview = tier", protection)
    self.assertIn('GroupBox("Planned protection levels")', protection)

  def test_protection_page_is_compiled_into_native_preferences_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = ProtectionSettingsView.swift;", project)
    self.assertIn("fileRef = A10000000000000000000023;", project)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("A10000000000000000000022,", sources)

  def test_privacy_and_logs_navigation_is_a_separate_sidebar_page(self):
    nav = VIEW.read_text(encoding="utf-8")
    self.assertIn("case privacyAndLogs", nav)
    self.assertIn('case .privacyAndLogs: return "Privacy and Logs"', nav)
    self.assertIn('case .privacyAndLogs: return "hand.raised"', nav)
    self.assertIn("case .privacyAndLogs:\\n      PrivacyAndLogsSettingsView()".replace("\\n", "\n"), nav)
    self.assertIn('accessibilityIdentifier("mainPreferencesSidebar")', nav)
    for existing in ("case .general:", "case .browsers:", "case .security:"):
      self.assertIn(existing, nav)

  def test_privacy_and_logs_page_explains_capabilities_without_false_status(self):
    page = (ROOT / "PDFMagicOpenerApp" / "PrivacyAndLogsSettingsView.swift").read_text(
        encoding="utf-8")
    for required in (
        "struct PrivacyAndLogsSettingsView: View",
        'Text("Privacy and Logs")',
        'GroupBox("Local document processing")',
        'GroupBox("Logs and diagnostics")',
        'GroupBox("Privacy and log controls")',
        'accessibilityIdentifier("privacyAndLogsSettingsPage")',
        'accessibilityIdentifier("localProcessingSection")',
        'accessibilityIdentifier("diagnosticLogsSection")',
        'accessibilityIdentifier("privacyControlsSection")',
        "does not read, display, export, or clear log files",
        "No retention duration or logging status is asserted",
    ):
      with self.subTest(required=required):
        self.assertIn(required, page)
    # The only new action explicitly requests read-only history metadata.
    self.assertEqual(page.count("Button("), 1)
    self.assertIn('Button("Show recent scan results")', page)
    self.assertIn("recentScanHistory = RecentScanHistoryReader.load()", page)
    for forbidden in (
        "@AppStorage", "UserDefaults", "FileManager", "NSWorkspace",
        "Process(", "FileHandle(", "URLSession", "URLRequest",
        "write(to:", "removeItem(", "setDefault", "LSSetDefault",
        "onOpenURL", "DocumentGroup", "target-app.txt",
        "Toggle(", "Picker(", "Slider(", "onAppear",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, page)

  def test_privacy_and_logs_page_is_compiled_into_native_app(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertEqual(project.count("path = PrivacyAndLogsSettingsView.swift;"), 1)
    self.assertIn("fileRef = B18400000000000000000002;", project)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("B18400000000000000000001,", sources)

  def test_window_is_non_mutating_and_in_xcode_target(self):
    view = VIEW.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("MainPreferencesView.swift", project)
    for forbidden in (
        "Process(", "FileHandle(", "write(to:", "createFile(",
        "setDefault", "LSSetDefault", "clamscan", "onOpenURL",
        "DocumentGroup", "target-app.txt",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, view)


if __name__ == "__main__":
  unittest.main()
