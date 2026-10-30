#!/usr/bin/env python3
"""Regression coverage for the native app's explicit, standard macOS Quit command."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class NativeQuitActionTests(unittest.TestCase):
  def test_quit_command_is_in_the_application_menu(self):
    app = APP.read_text(encoding="utf-8")
    self.assertIn('CommandGroup(replacing: .appTermination)', app)
    self.assertIn('Button("Quit PDF Magic Opener")', app)
    self.assertIn('.keyboardShortcut("q", modifiers: [.command])', app)
    self.assertRegex(
        app,
        re.compile(
            r'Button\("Quit PDF Magic Opener"\)\s*\{\s*'
            r'NSApplication\.shared\.terminate\(nil\)\s*\}',
        ),
    )
    self.assertEqual(app.count('Button("Quit PDF Magic Opener")'), 1)
    self.assertEqual(app.count('NSApplication.shared.terminate(nil)'), 1)

  def test_quit_is_local_to_the_standalone_app(self):
    app = APP.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("WindowGroup", app)
    self.assertIn("MainPreferencesView()", app)
    self.assertIn("local.studio.pdfmagicopener.swiftui", project)
    self.assertNotIn("CFBundleDocumentTypes", project)
    # The exact preferences URL may activate this window, but never launch
    # documents or replace the native Quit command.
    self.assertEqual(app.count(".onOpenURL { url in"), 1)
    self.assertIn('guard url.absoluteString == "pdfmagicopener://preferences" else { return }',
                  app)
    for forbidden in (
        "Process(", "NSWorkspace", "DocumentGroup",
        "target-app.txt", "clamscan", "LSSetDefault",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, app)


if __name__ == "__main__":
  unittest.main()
