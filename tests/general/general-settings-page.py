#!/usr/bin/env python3
"""Verify the General preferences page and unrelated scanner safety."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
GENERAL = ROOT / "PDFMagicOpenerApp" / "GeneralSettingsView.swift"
MAIN = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class GeneralSettingsPageTests(unittest.TestCase):
  def test_general_navigation_selects_dedicated_page(self):
    main = MAIN.read_text(encoding="utf-8")
    self.assertIn("case general", main)
    self.assertIn("case .general:\n      GeneralSettingsView()", main)
    self.assertIn("@State private var selection: MainPreferenceSection? = .general", main)
    self.assertIn("case .browsers:", main)
    self.assertIn("case .security:", main)
    self.assertNotIn('title: "PDF Magic Opener",', main)

  def test_general_page_has_usable_read_only_content(self):
    page = GENERAL.read_text(encoding="utf-8")
    for expected in (
        "struct GeneralSettingsView: View",
        "ScrollView",
        'Text("General")',
        'Label("Document handling", systemImage: "doc.text")',
        'Label("Current configuration", systemImage: "gearshape")',
        "ClamAV",
        "selected application",
        'Picker("Browser for scanned PDFs", selection: Binding(',
        'accessibilityIdentifier("defaultPDFBrowserSelector")',
        'accessibilityIdentifier("generalSettingsPage")',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, page)

  def test_page_is_compiled_in_xcode_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = GeneralSettingsView.swift;", project)
    self.assertIn("path = DefaultPDFBrowserPreferences.swift;", project)
    self.assertIn("fileRef = A1000000000000000000001B;", project)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("A1000000000000000000001A,", sources)

  def test_general_page_cannot_mutate_preferences_or_bypass_scanning(self):
    page = GENERAL.read_text(encoding="utf-8")
    self.assertIn('Toggle("Show Scan Progress"', page)
    for prohibited in (
        "@AppStorage", "UserDefaults", "FileManager", "NSWorkspace",
        "Process(", "write(to:", "LSSetDefault", "setDefault",
        "onOpenURL", "DocumentGroup", "target-app.txt",
    ):
      with self.subTest(prohibited=prohibited):
        self.assertNotIn(prohibited, page)


if __name__ == "__main__":
  unittest.main()
