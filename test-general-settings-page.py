#!/usr/bin/env python3
"""Verify the standalone, read-only General preferences page (opener-0178)."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
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
        'accessibilityIdentifier("generalSettingsPage")',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, page)

  def test_page_is_compiled_in_xcode_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = GeneralSettingsView.swift;", project)
    self.assertIn("fileRef = A1000000000000000000001B;", project)
    self.assertIn("files = (A10000000000000000000001, A10000000000000000000012, A10000000000000000000016, A1000000000000000000001A,);", project)

  def test_general_page_cannot_mutate_preferences_or_bypass_scanning(self):
    page = GENERAL.read_text(encoding="utf-8")
    for prohibited in (
        "@AppStorage", "UserDefaults", "FileManager", "NSWorkspace",
        "Process(", "write(to:", "LSSetDefault", "setDefault",
        "onOpenURL", "DocumentGroup", "target-app.txt",
        "Button(", "Toggle(", "Picker(",
    ):
      with self.subTest(prohibited=prohibited):
        self.assertNotIn(prohibited, page)


if __name__ == "__main__":
  unittest.main()
