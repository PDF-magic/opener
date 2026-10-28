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
        "GeneralSettingsView()",
        'title: "Browsers"',
        'title: "Security"',
        'accessibilityIdentifier("mainPreferencesSidebar")',
    ):
      with self.subTest(required=required):
        self.assertIn(required, view)

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
