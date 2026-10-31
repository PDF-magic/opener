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
      "This welcome preserves your viewer choice",
      "only if you explicitly request it below",
      'Button("Set PDF Magic Opener as Default")',
      'accessibilityIdentifier("firstRunSetDefaultPDFAppButton")',
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

  def test_default_offer_is_opt_in_and_delegates_to_verified_handler(self):
    source = WELCOME.read_text(encoding="utf-8")
    action = (ROOT / "PDFMagicOpenerApp/PDFDefaultApplicationSettingsView.swift").read_text(
      encoding="utf-8"
    )
    self.assertIn(
      'Button("Set PDF Magic Opener as Default") {\n'
      '              setDefaultPDFAppOnUserRequest()\n'
      '            }', source
    )
    self.assertIn('accessibilityIdentifier("firstRunDefaultPDFAppResult")', source)
    self.assertIn("guard !isSettingDefault else { return }", source)
    self.assertIn(".disabled(isSettingDefault)", source)
    self.assertEqual(source.count("PDFDefaultApplicationAction.request("), 1)
    before_action, action_body = source.split(
      "  private func setDefaultPDFAppOnUserRequest() {", 1
    )
    self.assertNotIn("PDFDefaultApplicationAction.request(", before_action)
    self.assertNotIn(".onAppear(perform: setDefaultPDFAppOnUserRequest)", source)
    for required in (
      "at: PDFDefaultApplicationAction.installedHandler",
      "runHelper: PDFDefaultApplicationAction.launchInstalledHelper",
      "currentPDFHandler: PDFDefaultApplicationAction.currentPDFHandler",
      "isSettingDefault = false",
      "The default could not be verified.",
    ):
      with self.subTest(required=required):
        self.assertIn(required, action_body)
    # The delegated helper checks the installed scanner-gated bundle and
    # verifies Launch Services' observed PDF handler before claiming success.
    for required in (
      "guard verifiedHandler(at: application) else",
      "completion(currentPDFHandler() == handlerBundleID)",
      "process.arguments = []",
      "files.isExecutableFile(atPath: helper.path)",
    ):
      with self.subTest(required=required):
        self.assertIn(required, action)
    self.assertIn("Continue to Preferences", source)
    self.assertNotIn("UserDefaults.standard.set", source)
    self.assertNotIn("scan-and-open.py", source)

  def test_default_handler_change_is_optional_not_accepted_on_continue(self):
    source = WELCOME.read_text(encoding="utf-8")
    opt_out = (
      "You can decline any offer to make PDF Magic Opener your default PDF "
      "application and keep your current macOS PDF handler."
    )
    no_consent = (
      "Continuing to Preferences does not approve or make a "
      "default-handler change."
    )
    self.assertIn('Text("' + opt_out + " " + no_consent + '")', source)
    self.assertLess(source.index('Label("Your choice of PDF application"'),
                    source.index(opt_out))
    self.assertLess(source.index(no_consent),
                    source.index('Label("Existing settings are preserved"'))
    # This is disclosure only. No file-association or scanner operation.
    for forbidden in ("LSSetDefaultRoleHandlerForContentType",
                      "LSSetDefaultHandlerForURLScheme", "Process(",
                      "NSWorkspace(", "target-app.txt"):
      self.assertNotIn(forbidden, source)

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
