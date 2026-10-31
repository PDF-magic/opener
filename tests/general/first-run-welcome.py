#!/usr/bin/env python3
"""Validate the welcome is a first-run UI, not a scanner or setup mutation."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "PDFMagicOpenerApp/PDFMagicOpenerApp.swift"
WELCOME = ROOT / "PDFMagicOpenerApp/FirstRunWelcomeView.swift"
STATE = ROOT / "PDFMagicOpenerApp/FirstRunWelcomeState.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj"
CI = ROOT / ".github/workflows/ci.yml"


class FirstRunWelcomeTests(unittest.TestCase):
  def test_main_window_routes_through_welcome_and_preserves_preferences(self):
    source = APP.read_text(encoding="utf-8")
    self.assertIn("WindowGroup(\"PDF Magic Opener\")", source)
    self.assertIn("FirstRunWelcomeGate {\n        MainPreferencesView()", source)
    self.assertIn("Settings {\n      MainPreferencesView()", source)
    self.assertIn("InitialConfiguration.createIfNeeded()", source)
    self.assertIn('url.absoluteString == "pdfmagicopener://preferences"', source)
    self.assertNotIn("DocumentGroup", source)

  def test_welcome_has_clear_accurate_non_mutating_content(self):
    source = WELCOME.read_text(encoding="utf-8")
    for expected in (
      "struct FirstRunWelcomeGate<Content: View>: View",
      "struct FirstRunWelcomeView: View",
      "FirstRunWelcomeState.shouldShow()",
      "if welcomePending",
      "FirstRunWelcomeState.acknowledge()",
      "welcomePending = false",
      'Label("Welcome to PDF Magic Opener"',
      "ClamAV", "blocks opening",
      "does not change either selection",
      "does not install software",
      'Button("Continue to Preferences", action: onContinue)',
      'accessibilityIdentifier("firstRunWelcomeScreen")',
      'accessibilityIdentifier("firstRunContinueButton")',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)
    self.assertLess(source.index("FirstRunWelcomeState.acknowledge()"),
                    source.index("welcomePending = false"))
    for forbidden in ("Process(", "NSWorkspace(", "LSSetDefault",
                      "FileManager", "clamscan(", "scan_and_open",
                      "target-app.txt", "DocumentGroup", "write(to:",
                      "UserDefaults.standard.set", "removePersistentDomain"):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)

  def test_first_run_explains_the_actual_pdf_opening_workflow(self):
    source = WELCOME.read_text(encoding="utf-8")
    purpose = (
      "When configured as your PDF handler, PDF Magic Opener uses local "
      "ClamAV checks before opening a PDF in your chosen application. "
      "If a clean result and recent signatures cannot be verified, "
      "opening is blocked."
    )
    self.assertIn('Text("' + purpose + '")', source)
    # A user must encounter the explanation before navigating the details.
    self.assertLess(source.index(purpose),
                    source.index('Label("Local malware scanning"'))
    self.assertIn("Continue to Preferences", source)
    # No claim that opening the preferences window enables PDF handling.
    self.assertNotIn("automatically sets your default", source.lower())
    self.assertNotIn("guarantees safety", source.lower())

  def test_finder_quick_action_is_offered_without_silent_configuration(self):
    source = WELCOME.read_text(encoding="utf-8")
    for expected in (
      'Label("Optional Finder Quick Action"',
      'Button("Configure Finder Quick Action…")',
      'showingFinderQuickActionSetup = true',
      'if showingFinderQuickActionSetup',
      'The installer requires an existing “Allow and Open” Quick Action.',
      'install-allow-and-open.sh',
      'without sudo',
      'unrecognized or customized Finder action is not silently replaced',
      'Button("Not now")',
      'showingFinderQuickActionSetup = false',
      'accessibilityIdentifier("firstRunConfigureFinderQuickActionButton")',
      'accessibilityIdentifier("firstRunFinderQuickActionInstructions")',
      'https://github.com/PDF-magic/opener#installation-and-usage',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, source)
    # Merely showing the offer, deferring it, or following the guide must
    # never acknowledge first run or touch the scanning/installation path.
    setup = source.split('Label("Optional Finder Quick Action"', 1)[1].split(
      "\n          }\n          .fixedSize", 1)[0]
    for forbidden in ("FirstRunWelcomeState.acknowledge()", "Process(",
                      "NSWorkspace", "FileManager", "UserDefaults", "clamscan",
                      "scan_and_open", "LSSetDefault", "write(to:"):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, setup)

  def test_acknowledgement_has_no_automatic_startup_side_effects(self):
    state = STATE.read_text(encoding="utf-8")
    self.assertIn('acknowledgementKey = "firstRunWelcomeAcknowledged.v1"', state)
    self.assertIn("static func shouldShow(defaults: UserDefaults = .standard)", state)
    self.assertIn("static func acknowledge(defaults: UserDefaults = .standard)", state)
    self.assertEqual(state.count("defaults.set("), 1)
    self.assertNotIn("removePersistentDomain", state)
    self.assertNotIn("synchronize()", state)

  def test_welcome_is_built_and_covered_by_native_and_portable_ci(self):
    project = PROJECT.read_text(encoding="utf-8")
    for path in ("FirstRunWelcomeView.swift", "FirstRunWelcomeState.swift"):
      self.assertEqual(project.count("path = " + path + ";"), 1)
    sources = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
      "runOnlyForDeploymentPostprocessing", 1)[0]
    for ident in ("B96800000000000000000001,", "B96800000000000000000003,"):
      self.assertIn(ident, sources)
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("tests/general/first-run-welcome.py -v", ci)
    self.assertIn("test-first-run-welcome.swift", ci)
    self.assertIn("TestFirstRunWelcome", ci)


if __name__ == "__main__":
  unittest.main()
