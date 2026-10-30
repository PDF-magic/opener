#!/usr/bin/env python3
"""Verify opener-0199's conditional no-login-item decision stays scanner-safe."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "PDFMagicOpenerApp"
ENTRY = APP / "PDFMagicOpenerApp.swift"
GENERAL = APP / "GeneralSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
INSTALLER = ROOT / "install-allow-and-open.sh"
SCANNER = ROOT / "brave-pdf-opener.swift"
DOC = ROOT / "docs" / "launch-at-login-decision.md"


class LaunchAtLoginDecisionTests(unittest.TestCase):
  def test_preferences_app_has_no_startup_registration_or_login_toggle(self):
    for path in sorted(APP.glob("*.swift")):
      source = path.read_text(encoding="utf-8")
      for forbidden in (
        "import ServiceManagement", "SMAppService.",
        "SMLoginItemSetEnabled", "LSSharedFileListInsertItemURL",
        "launchctl bootstrap", "LoginItem(", "LaunchAtLogin(",
        'Toggle("Launch at Login"', 'Toggle("Open at Login"',
      ):
        with self.subTest(path=path.name, forbidden=forbidden):
          self.assertNotIn(forbidden, source)
    app = ENTRY.read_text(encoding="utf-8")
    general = GENERAL.read_text(encoding="utf-8")
    self.assertIn('WindowGroup("PDF Magic Opener")', app)
    self.assertIn("MainPreferencesView()", app)
    self.assertIn("Settings {", app)
    self.assertIn('Button("Quit PDF Magic Opener")', app)
    self.assertIn("PDFDefaultApplicationSettingsView()", general)
    self.assertIn('Picker("Browser for scanned PDFs"', general)
    self.assertIn("Launch-at-login decision (opener-0199)", app)

  def test_no_preferences_login_agent_or_background_target(self):
    project = PROJECT.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    self.assertEqual(project.count("INFOPLIST_KEY_LSUIElement = NO;"), 2)
    self.assertNotIn("INFOPLIST_KEY_LSBackgroundOnly = YES;", project)
    self.assertNotIn("SMAppService", project)
    self.assertNotIn("SMLoginItem", project)
    self.assertNotIn("local.studio.pdfmagicopener.swiftui", installer)
    self.assertNotIn("PDFMagicOpenerApp.swift", installer)

  def test_pdf_scanning_and_signature_updater_remain_independent(self):
    scanner = SCANNER.read_text(encoding="utf-8")
    installer = INSTALLER.read_text(encoding="utf-8")
    self.assertIn("func application(_ application: NSApplication, open urls: [URL])", scanner)
    self.assertIn("'CFBundleIdentifier': 'local.studio.brave-pdf-opener'", installer)
    self.assertIn("'LSItemContentTypes': ['com.adobe.pdf']", installer)
    self.assertIn("'CFBundleExecutable': 'PDFOpener'", installer)
    self.assertIn("'Label': 'local.studio.pdf-malware-signatures'", installer)
    self.assertIn("'StartInterval': 14400", installer)
    self.assertIn("'RunAtLoad': True", installer)
    self.assertIn("'update-malware-signatures.sh'", installer)
    # Do not mistake the existing updater agent for a preferences login item.
    agent = installer.split("agent = {", 1)[1].split("\n}", 1)[0]
    self.assertNotIn("pdfmagicopener.swiftui", agent)
    self.assertNotIn("PDFMagicOpenerApp", agent)

  def test_decision_is_explicit_conditional_and_documented(self):
    text = DOC.read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for phrase in (
      "Decision: do not add a Launch at Login option",
      "separately installed PDF handler",
      "local.studio.pdf-malware-signatures",
      "When to reconsider",
      "SMAppService",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, text)
    self.assertIn("Launch at Login (opener-0199)", readme)
    self.assertIn("docs/launch-at-login-decision.md", readme)


if __name__ == "__main__":
  unittest.main()
