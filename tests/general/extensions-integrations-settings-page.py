#!/usr/bin/env python3
"""Verify the Extensions and Integrations preferences page and safety boundary."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
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

  def test_extension_connection_indicator_is_visible_accessible_and_fail_closed(self):
    page = PAGE.read_text(encoding="utf-8")
    for expected in (
        'GroupBox("Extension connection")',
        'Image(systemName: "circle.fill")',
        'Text("Not connected")',
        'accessibilityElement(children: .combine)',
        'accessibilityLabel("Extension connection: Not connected")',
        'accessibilityIdentifier("extensionConnectionStatus")',
        'accessibilityIdentifier("extensionConnectionSection")',
        "No verified browser-to-app connection is available",
        "not a malware scan result or permission to open a PDF",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, page)
    self.assertNotIn('Text("Connected")', page)
    self.assertNotIn('accessibilityLabel("Extension connection: Connected")', page)
    # The indicator is explicitly read-only until an authenticated browser
    # connection exists. Keep existing scanner and preference safety tests.
    self.assertNotIn("connectNative(", page)
    self.assertNotIn("sendNativeMessage(", page)

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


  def test_extensions_source_root_exists_without_enabling_an_extension(self):
    # Git cannot track empty directories, so an inert README establishes the
    # source root without adding a built extension or changing app behavior.
    source_root = ROOT / "extensions"
    self.assertTrue(source_root.is_dir())
    guide = (source_root / "README.md").read_text(encoding="utf-8")
    self.assertIn("source-only scaffold", guide)
    self.assertIn("not an installed or enabled extension", guide)
    self.assertIn("ClamAV", guide)
    self.assertIn("user-selected application", guide)

    # The existing native settings page and its scanner tests remain wired;
    # the source directory itself is not an extension activation action.
    page = PAGE.read_text(encoding="utf-8")
    self.assertIn("This page does not install, enable, or disable extensions", page)
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("python3 tests/general/extensions-integrations-settings-page.py -v", ci)


if __name__ == "__main__":
  unittest.main()
