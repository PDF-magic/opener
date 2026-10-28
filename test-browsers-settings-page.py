#!/usr/bin/env python3
"""Verify the dedicated Browsers preferences page is wired into the SwiftUI app."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
BROWSERS = ROOT / "PDFMagicOpenerApp" / "BrowsersSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class BrowsersSettingsPageTests(unittest.TestCase):
  def test_sidebar_routes_to_a_dedicated_browsers_page(self):
    source = MAIN.read_text(encoding="utf-8")
    self.assertIn("case browsers", source)
    self.assertIn('case .browsers: return "Browsers"', source)
    self.assertRegex(source, r"case \.browsers:\s+BrowsersSettingsView\(\)")
    self.assertIn('accessibilityIdentifier("mainPreferencesSidebar")', source)

  def test_browser_page_has_discovery_destination_and_custom_sections(self):
    source = BROWSERS.read_text(encoding="utf-8")
    self.assertIn("struct BrowsersSettingsView: View", source)
    for required in (
        'Text("Browsers")', 'GroupBox("Installed browsers")',
        'GroupBox("Preferred PDF application")',
        'GroupBox("Additional applications")',
        'accessibilityIdentifier("browsersSettingsPage")',
        'accessibilityIdentifier("installedBrowsersSection")',
        'accessibilityIdentifier("preferredBrowserSection")',
        'accessibilityIdentifier("customBrowserSection")',
    ):
      with self.subTest(required=required):
        self.assertIn(required, source)

  def test_browser_page_is_read_only_and_compiled_into_app(self):
    source = BROWSERS.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = BrowsersSettingsView.swift;", project)
    self.assertIn("fileRef = A10000000000000000000021;", project)
    self.assertRegex(project, r"files = \([^\n]*A10000000000000000000020,")
    self.assertRegex(project, r"children = \([^\n]*A10000000000000000000021,")
    for forbidden in (
        "Process(", "NSWorkspace", "FileHandle(", "UserDefaults",
        "onOpenURL", "DocumentGroup", "clamscan",
        "LSSetDefault", "write(to:", "removeItem(", "setDefault",
        "target-app.txt",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)


if __name__ == "__main__":
  unittest.main()
