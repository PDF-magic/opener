#!/usr/bin/env python3
"""Ensure the standalone SwiftUI app exposes a real, safe main preferences window."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
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
        'title: "PDF Magic Opener"',
        'title: "Browsers"',
        'case .security: return "Protection"',
        'ProtectionSettingsView()',
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
        "Toggle(", "Button(",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, protection)

  def test_protection_page_is_compiled_into_native_preferences_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = ProtectionSettingsView.swift;", project)
    self.assertIn("fileRef = A10000000000000000000023;", project)
    self.assertIn("A10000000000000000000022,);", project)

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
