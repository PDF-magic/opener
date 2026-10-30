#!/usr/bin/env python3
"""Confirm the macOS Settings command uses the native, non-mutating settings scene."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
VIEW = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
README = ROOT / "README.md"


class SettingsShortcutTests(unittest.TestCase):
  def test_native_settings_scene_has_standard_command_comma_shortcut(self):
    source = APP.read_text(encoding="utf-8")
    pattern = (
      r'Settings\s*\{\s*MainPreferencesView\(\)\s*\}'
      r'\s*\.keyboardShortcut\(",",\s*modifiers:\s*\.command\)'
    )
    self.assertRegex(source, pattern)
    self.assertEqual(len(re.findall(r'\bSettings\s*\{', source)), 1,
                     "Only one system Settings menu/window should be registered")

  def test_shortcut_opens_existing_preferences_not_an_unrelated_window(self):
    source = APP.read_text(encoding="utf-8")
    view = VIEW.read_text(encoding="utf-8")
    self.assertIn('WindowGroup("PDF Magic Opener")', source)
    self.assertEqual(source.count("MainPreferencesView()"), 2,
                     "Both main window and Settings command use the same view")
    self.assertIn("struct MainPreferencesView: View", view)
    self.assertIn("NavigationSplitView", view)
    # The only incoming URL may raise this same preferences window. It is
    # never a PDF document handler, scanner shortcut, or arbitrary URL launcher.
    self.assertEqual(source.count(".onOpenURL { url in"), 1)
    self.assertIn('guard url.absoluteString == "pdfmagicopener://preferences" else { return }',
                  source)
    for forbidden in (
      "CommandGroup(replacing: .appSettings)", "NSEvent", "NSWorkspace", "openURL(",
      "Process(", "clamscan", "target-app.txt",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)

  def test_shortcut_is_documented(self):
    readme = README.read_text(encoding="utf-8")
    self.assertIn("Command-comma", readme)
    self.assertIn("Settings…", readme)


if __name__ == "__main__":
  unittest.main()
