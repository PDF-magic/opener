#!/usr/bin/env python3
"""Verify the dedicated Updates preferences page is safely wired into SwiftUI."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
UPDATES = ROOT / "PDFMagicOpenerApp" / "UpdatesSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class UpdatesSettingsPageTests(unittest.TestCase):
  def test_updates_navigation_is_dedicated_and_general_remains_default(self):
    source = MAIN.read_text(encoding="utf-8")
    for expected in (
        "case updates", 'case .updates: return "Updates"',
        'case .updates: return "arrow.triangle.2.circlepath"',
        "case .updates:\n      UpdatesSettingsView()",
        "@State private var selection: MainPreferenceSection? = .general",
        "case .general:\n      GeneralSettingsView()",
        "case .browsers:", "case .security:",
        'accessibilityIdentifier("mainPreferencesSidebar")',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)

  def test_updates_page_describes_both_update_categories_without_false_status(self):
    source = UPDATES.read_text(encoding="utf-8")
    for expected in (
        "struct UpdatesSettingsView: View",
        'Text("Updates")',
        'GroupBox("Application updates")',
        'GroupBox("Malware definition updates")',
        'object(forInfoDictionaryKey: "CFBundleShortVersionString")',
        'LabeledContent("Installed version", value: applicationVersion)',
        "not available from this page yet",
        "existing scanner update workflow",
        'accessibilityIdentifier("updatesSettingsPage")',
        'accessibilityIdentifier("applicationUpdatesSection")',
        'accessibilityIdentifier("malwareDefinitionUpdatesSection")',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)
    self.assertNotIn("Up to date", source)
    self.assertNotIn("Last checked", source)

  def test_page_belongs_to_native_app_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = UpdatesSettingsView.swift;", project)
    self.assertIn("fileRef = B18200000000000000000002;", project)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("B18200000000000000000001,", sources)
    self.assertEqual(project.count("path = UpdatesSettingsView.swift;"), 1)

  def test_updates_page_does_not_install_or_mutate(self):
    source = UPDATES.read_text(encoding="utf-8")
    for forbidden in (
        "@AppStorage", "UserDefaults", "FileManager", "NSWorkspace",
        "Process(", "URLSession", "URLRequest", "downloadTask",
        "write(to:", "LSSetDefault", "setDefault", "onOpenURL",
        "DocumentGroup", "target-app.txt", "Button(", "Toggle(",
        "Picker(", "Task {", "onAppear", "onChange",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)


if __name__ == "__main__":
  unittest.main()
