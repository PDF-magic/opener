#!/usr/bin/env python3
"""Verify the native About and Diagnostics page is distinct and read-only."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
NAV = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
PAGE = ROOT / "PDFMagicOpenerApp" / "AboutAndDiagnosticsSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"


class AboutDiagnosticsPageTests(unittest.TestCase):
  def test_sidebar_exposes_a_dedicated_page(self):
    nav = NAV.read_text(encoding="utf-8")
    for text in (
      "case aboutAndDiagnostics",
      'case .aboutAndDiagnostics: return "About and Diagnostics"',
      'case .aboutAndDiagnostics: return "info.circle"',
      "case .aboutAndDiagnostics:\n      AboutAndDiagnosticsSettingsView()",
      "List(MainPreferenceSection.allCases",
      "GeneralSettingsView()",
      "BrowsersSettingsView()",
      "ProtectionSettingsView()",
      "AdvancedScanningSettingsView()",
    ):
      with self.subTest(text=text):
        self.assertIn(text, nav)

  def test_about_page_shows_real_bundle_and_os_information(self):
    page = PAGE.read_text(encoding="utf-8")
    for text in (
      "struct AboutAndDiagnosticsSettingsView: View",
      'Text("About and Diagnostics")',
      'object(forInfoDictionaryKey: "CFBundleShortVersionString")',
      'object(forInfoDictionaryKey: "CFBundleVersion")',
      "Bundle.main.bundleIdentifier",
      "ProcessInfo.processInfo.operatingSystemVersionString",
      'GroupBox("Application")',
      'GroupBox("Environment")',
      'GroupBox("Scanning diagnostics")',
      'accessibilityIdentifier("aboutDiagnosticsApplicationSection")',
      'accessibilityIdentifier("aboutDiagnosticsEnvironmentSection")',
      'accessibilityIdentifier("aboutDiagnosticsScannerSection")',
      'accessibilityIdentifier("aboutAndDiagnosticsSettingsPage")',
      "are not checked by this page",
      "does not read, collect, or export scan logs",
    ):
      with self.subTest(text=text):
        self.assertIn(text, page)

  def test_page_does_not_undermine_scan_safety_or_read_secrets(self):
    page = PAGE.read_text(encoding="utf-8")
    for forbidden in (
      "Button(", "Toggle(", "Picker(", "Slider(", "UserDefaults",
      "@AppStorage", "FileManager", "NSWorkspace", "Process(",
      "FileHandle(", "readData(", "write(to:", "createFile(",
      "removeItem(", "contentsOf:", "clamscan(", "LSSetDefault",
      "target-app.txt", "getenv(", "environment[", "onOpenURL",
      "DocumentGroup", "URLSession",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, page)

  def test_source_is_compiled_and_existing_about_menu_remains(self):
    project = PROJECT.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    self.assertIn("path = AboutAndDiagnosticsSettingsView.swift;", project)
    self.assertIn("fileRef = B18600000000000000000002;", project)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
      "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("B18600000000000000000001,", sources)
    self.assertIn('Window("About PDF Magic Opener", id: "about")', app)
    self.assertIn("AboutView()", app)
    self.assertIn("CommandGroup(replacing: .appInfo)", app)


if __name__ == "__main__":
  unittest.main()
