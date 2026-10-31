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
      'Button("Continue to Preferences", action: finishSetup)',
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

  def test_initial_protection_choice_is_explicit_and_non_enforcing(self):
    view = WELCOME.read_text(encoding="utf-8")
    shared = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text(
      encoding="utf-8")
    scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    for expected in (
      "Choose your initial protection preference",
      "Built-in ClamAV scanning and fail-closed opening remain the only active protection.",
      "Preferred future protection profile",
      "PreferredProtectionLevel.standard",
      "PreferredProtectionLevel.enhanced",
      "PreferredProtectionLevel.maximum",
      'accessibilityIdentifier("firstRunProtectionProfilePicker")',
      "InitialProtectionProfileChoice.save(initialProfile)",
      ".disabled(initialProfile == nil)",
      'accessibilityIdentifier("firstRunProtectionSaveError")',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, view)
    self.assertLess(view.index("InitialProtectionProfileChoice.save(initialProfile)"),
                    view.index("onContinue()"))
    self.assertIn("guard let choice else { return false }", shared)
    self.assertIn(
      "PlannedProtectionLevelPreference.saveExplicitChoice(choice, defaults: defaults)",
      shared)
    self.assertIn("SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn",
                  shared)
    self.assertNotIn("SelectedProtectionProfilePreference.save(", view)
    self.assertIn("if not cached_clean(cache_id):", scanner)
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("test-first-run-profile-choice.swift", ci)

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
