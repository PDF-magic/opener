#!/usr/bin/env python3
"""Verify the Extensions and Integrations preferences page and safety boundary."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp"
MAIN = APP / "MainPreferencesView.swift"
PAGE = APP / "ExtensionsAndIntegrationsSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class ExtensionsAndIntegrationsSettingsTests(unittest.TestCase):
  def test_sidebar_has_distinct_route_and_symbol(self):
    main = MAIN.read_text(encoding="utf-8")
    self.assertIn("case extensionsAndIntegrations", main)
    self.assertIn('case .extensionsAndIntegrations: return "Extensions and Integrations"', main)
    self.assertIn('case .extensionsAndIntegrations: return "puzzlepiece.extension"', main)
    self.assertRegex(
        main,
        r"case \.extensionsAndIntegrations:\s+ExtensionsAndIntegrationsSettingsView\(\)",
    )
    for previous in ("GeneralSettingsView()", "BrowsersSettingsView()", "ProtectionSettingsView()"):
      with self.subTest(previous=previous):
        self.assertIn(previous, main)

  def test_page_has_accessible_integration_sections(self):
    page = PAGE.read_text(encoding="utf-8")
    for expected in (
        "struct ExtensionsAndIntegrationsSettingsView: View",
        'Text("Extensions and Integrations")',
        'GroupBox("Finder integration")',
        'GroupBox("Browser and application handoff")',
        'GroupBox("Extensions")',
        'accessibilityIdentifier("finderIntegrationSection")',
        'accessibilityIdentifier("browserIntegrationSection")',
        'accessibilityIdentifier("extensionsSection")',
        'accessibilityIdentifier("extensionsAndIntegrationsSettingsPage")',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, page)

  def test_page_is_compiled_with_other_native_views(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = ExtensionsAndIntegrationsSettingsView.swift;", project)
    self.assertIn("fileRef = E18500000000000000000002;", project)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("E18500000000000000000001,", sources)
    for name in ("GeneralSettingsView.swift", "BrowsersSettingsView.swift",
                 "ProtectionSettingsView.swift"):
      self.assertIn(name, project)

  def test_page_does_not_toggle_extensions_or_change_scan_security(self):
    page = PAGE.read_text(encoding="utf-8")
    for prohibited in (
        "@AppStorage", "@State", "UserDefaults", "FileManager", "NSWorkspace",
        "Process(", "FileHandle(", "write(to:", "onOpenURL", "DocumentGroup",
        "LSSetDefault", "setDefault", "clamscan(", "target-app.txt",
        "Button(", "Toggle(", "Picker(", "Link(",
    ):
      with self.subTest(prohibited=prohibited):
        self.assertNotIn(prohibited, page)


if __name__ == "__main__":
  unittest.main()
