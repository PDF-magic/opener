#!/usr/bin/env python3
"""Verify first-run browser inventory is passive and uses the installed picker."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WELCOME = ROOT / "PDFMagicOpenerApp/FirstRunWelcomeView.swift"
PICKER = ROOT / "PDFMagicOpenerApp/DefaultPDFBrowserPreferences.swift"
CI = ROOT / ".github/workflows/ci.yml"


class FirstRunBrowsersTests(unittest.TestCase):
  def test_first_run_detects_browsers_on_appearance(self):
    source = WELCOME.read_text(encoding="utf-8")
    self.assertIn("@State private var installedBrowsers: [PDFBrowserOption] = []", source)
    self.assertIn("@State private var hasCheckedBrowsers = false", source)
    self.assertIn("private func detectInstalledBrowsers()", source)
    self.assertIn("installedBrowsers = DefaultPDFBrowserPreferences.discover()", source)
    self.assertIn("hasCheckedBrowsers = true", source)
    self.assertIn(".onAppear(perform: detectInstalledBrowsers)", source)

  def test_inventory_displays_real_results_and_empty_state_accessibly(self):
    source = WELCOME.read_text(encoding="utf-8")
    for item in (
      'Label("Installed browsers", systemImage: "globe")',
      "if !hasCheckedBrowsers",
      "else if installedBrowsers.isEmpty",
      "ForEach(installedBrowsers) { browser in",
      "Label(browser.name, systemImage: \"globe\")",
      'accessibilityIdentifier("firstRunBrowserDetectionPending")',
      'accessibilityIdentifier("firstRunNoBrowsersDetected")',
      'accessibilityIdentifier("firstRunDetectedBrowser-\\(browser.id)")',
      'accessibilityIdentifier("firstRunBrowserDetectionPrivacy")',
      "registered with macOS",
      "not a browser selection",
    ):
      with self.subTest(item=item):
        self.assertIn(item, source)

  def test_reuses_verified_read_only_discovery_without_mutating_preferences(self):
    welcome = WELCOME.read_text(encoding="utf-8")
    picker = PICKER.read_text(encoding="utf-8")
    for item in (
      "NSWorkspace.shared.urlsForApplications(withBundleIdentifier:",
      'app.pathExtension.lowercased() == "app"',
      "bundle.bundleIdentifier == identifier",
      "isExecutable(executable.path)",
      "return PDFBrowserOption(id: identifier, name: name, applicationURL: app)",
    ):
      self.assertIn(item, picker)
    for forbidden in (
      "saveVerified(", "currentSelection(", "Process(", "open(", "scanAndOpen(",
      "UserDefaults.standard.set", "LSSetDefault", "removePersistentDomain",
      "target-app.txt", "ClamAVScanner", "NSWorkspace.shared.open",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, welcome)
    self.assertLess(welcome.index("detectInstalledBrowsers()"),
                    welcome.index('Button("Continue to Preferences", action: onContinue)'))
    self.assertIn("FirstRunWelcomeState.acknowledge()", welcome)
    self.assertNotIn("FirstRunWelcomeState.acknowledge()", welcome.split(
      "private func detectInstalledBrowsers()", 1
    )[1].split("var body: some View", 1)[0])

  def test_ci_covers_both_wiring_and_real_native_discovery(self):
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("tests/general/first-run-browsers.py -v", ci)
    self.assertIn("test-first-run-browsers.swift", ci)
    self.assertIn('"$RUNNER_TEMP/TestFirstRunBrowsers"', ci)
    self.assertIn("PDFMagicOpenerApp/DefaultPDFBrowserPreferences.swift", ci)


if __name__ == "__main__":
  unittest.main()
