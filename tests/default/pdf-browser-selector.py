#!/usr/bin/env python3
"""Validate the native General default-PDF-browser picker and its safe handoff."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
GENERAL = ROOT / "PDFMagicOpenerApp" / "GeneralSettingsView.swift"
HELPER = ROOT / "PDFMagicOpenerApp" / "DefaultPDFBrowserPreferences.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
INSTALLED = ROOT / "select-custom-pdf-application.py"
REGISTRY = ROOT / "browser_registry.py"


class GeneralDefaultPDFBrowserSelectorTests(unittest.TestCase):
  def test_general_shows_native_selector_without_automatic_save(self):
    source = GENERAL.read_text(encoding="utf-8")
    for expected in (
        'GroupBox("Default PDF browser")',
        'Picker("Browser for scanned PDFs", selection: Binding(',
        'accessibilityIdentifier("defaultPDFBrowserSelector")',
        'accessibilityIdentifier("defaultPDFBrowserStatus")',
        "ForEach(browserOptions)",
        "selectedBrowserID = saved",
        "browserOptions = DefaultPDFBrowserPreferences.discover()",
        "DefaultPDFBrowserPreferences.currentSelection()",
        "DefaultPDFBrowserPreferences.saveVerified(option)",
        ".onAppear { loadBrowserSelection() }",
        "guard !savingBrowser, identifier != selectedBrowserID,",
        "if saved {",
        "selectedBrowserID = identifier",
        "Existing selection (not in installed browser list)",
        ".disabled(savingBrowser || browserOptions.isEmpty)",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)
    init = source.split("private func loadBrowserSelection()", 1)[1].split(
        "private func selectBrowser", 1)[0]
    self.assertNotIn("saveVerified", init)
    failure = source.split("if saved {", 1)[1].split("}", 2)[1]
    self.assertNotIn("selectedBrowserID =", failure)

  def test_inventory_requires_supported_exact_installed_executable_bundle(self):
    helper = HELPER.read_text(encoding="utf-8")
    registry = REGISTRY.read_text(encoding="utf-8")
    supported = set(re.findall(r'"(?:brave|chrome|chromium|edge|vivaldi|opera|arc|firefox|safari)": "([^"]+)"', registry))
    identifiers = set(re.findall(r'\("([^"]+)", "(?:Brave|Google Chrome|Chromium|Microsoft Edge|Vivaldi|Opera|Arc|Firefox|Safari)"\)', helper))
    self.assertEqual(identifiers, supported)
    for assertion in (
        "NSWorkspace.shared.urlsForApplications(withBundleIdentifier:",
        "candidate.standardizedFileURL.resolvingSymlinksInPath()",
        'app.pathExtension.lowercased() == "app"',
        "bundle.bundleIdentifier == identifier",
        "isExecutable(executable.path)",
        "return nil",
    ):
      with self.subTest(assertion=assertion):
        self.assertIn(assertion, helper)

  def test_preference_reads_safely_and_preserves_existing_custom_values(self):
    source = HELPER.read_text(encoding="utf-8")
    for assertion in (
        "target-app.txt", "O_DIRECTORY | O_NOFOLLOW",
        'openat(parentFD, "target-app.txt", O_RDONLY | O_NOFOLLOW)',
        "fstat(fileFD, &info)", "S_IFREG", "count <= 256",
        'identifier == "system-default-browser"',
        "return errno == ENOENT", "com.brave.Browser",
    ):
      with self.subTest(assertion=assertion):
        self.assertIn(assertion, source)
    self.assertNotIn("UserDefaults", source)
    self.assertNotIn("try? Data.write", source)

  def test_saves_only_through_installed_verified_atomic_chooser(self):
    source = HELPER.read_text(encoding="utf-8")
    installed = INSTALLED.read_text(encoding="utf-8")
    for assertion in (
        '"select-custom-pdf-application.py"',
        "values.isRegularFile == true",
        "values.isSymbolicLink != true",
        '"/usr/bin/python3"',
        '"--application", option.applicationURL.path',
        "process.terminationStatus == 0",
    ):
      with self.subTest(assertion=assertion):
        self.assertIn(assertion, source)
    for assertion in (
        "def choose_and_save(", "PDF_VERIFIER", "def persist_preference(",
        "os.O_EXCL | os.O_NOFOLLOW", "os.replace(", "os.fsync(",
        "if verified.returncode != 0:", "persist_preference(identifier, destination)",
    ):
      with self.subTest(assertion=assertion):
        self.assertIn(assertion, installed)
    self.assertNotIn("Process(executableURL:", source)
    self.assertNotIn("/bin/sh", source)

  def test_compiled_in_app_target_and_other_controls_are_unchanged(self):
    project = PROJECT.read_text(encoding="utf-8")
    general = GENERAL.read_text(encoding="utf-8")
    self.assertIn("path = DefaultPDFBrowserPreferences.swift;", project)
    self.assertIn("fileRef = B19500000000000000000002;", project)
    phase = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("B19500000000000000000001,", phase)
    for expected in (
        'Label("Document handling", systemImage: "doc.text")',
        'Label("Current configuration", systemImage: "gearshape")',
        'accessibilityIdentifier("generalSettingsPage")',
    ):
      self.assertIn(expected, general)
    self.assertNotIn("LSSetDefault", general)
    self.assertNotIn("clamscan(", general)


if __name__ == "__main__":
  unittest.main()
