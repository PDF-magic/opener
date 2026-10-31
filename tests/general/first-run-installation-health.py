#!/usr/bin/env python3
"""Read-only first-run installation health checks and isolated native fixtures."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp/FirstRunWelcomeView.swift"
MODEL = ROOT / "PDFMagicOpenerApp/FirstRunInstallationHealth.swift"
NATIVE = ROOT / "test-first-run-installation-health.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj"
CI = ROOT / ".github/workflows/ci.yml"


class FirstRunInstallationHealthTests(unittest.TestCase):
  def test_welcome_runs_on_appearance_and_can_recheck(self):
    view = VIEW.read_text(encoding="utf-8")
    self.assertIn("private func runBasicInstallationHealthCheck()", view)
    self.assertIn("FirstRunSignatureAvailability.readInstalled()", view)
    self.assertIn("PDFDefaultApplicationAction.verifiedHandler(", view)
    self.assertIn("readGeneralPDFHandlerStatus()", view)
    self.assertIn("FirstRunInstallationHealth.assess(", view)
    self.assertIn(".onAppear(perform: runBasicInstallationHealthCheck)", view)
    self.assertIn('GroupBox("Basic installation health check")', view)
    self.assertIn('Button("Check Installation Again", action: runBasicInstallationHealthCheck)', view)
    for name in ("firstRunInstallationHealthSection",
                 "firstRunInstallationHealthSummary",
                 "firstRunInstallationHandlerStatus",
                 "firstRunInstallationSignaturesStatus",
                 "firstRunInstallationPDFAssociationStatus",
                 "firstRunCheckInstallationAgain"):
      self.assertIn(f'accessibilityIdentifier("{name}")', view)

  def test_diagnostics_never_change_installed_protection_or_user_choices(self):
    view = VIEW.read_text(encoding="utf-8")
    probe = view.split("private func runBasicInstallationHealthCheck()", 1)[1].split(
      "private func loadBrowserChoice()", 1
    )[0]
    for unsafe in ("Process(", "saveVerified(", "UserDefaults.standard.set",
                   "LSSetDefault", "launchInstalledHelper(", "scanAndOpen(",
                   "request(", "FileManager.default.create", "write("):
      with self.subTest(unsafe=unsafe):
        self.assertNotIn(unsafe, probe)
    model = MODEL.read_text(encoding="utf-8")
    self.assertIn("does not run ClamAV", model)
    self.assertIn("native scan gate remains mandatory", model)
    self.assertIn("Another application is the macOS PDF default", model)
    self.assertNotIn("Process(", model)
    self.assertNotIn("FileManager", model)
    self.assertNotIn("UserDefaults", model)
    self.assertNotIn("LSSetDefault", model)

  def test_native_matrix_and_existing_ci_wiring(self):
    test = NATIVE.read_text(encoding="utf-8")
    for expected in ("Health.SignatureFiles.missing", ".incomplete", ".unsafe",
                     "handlerInstalled: false", "Health.PDFAssociation.anotherApplication",
                     "Health.PDFAssociation.unknown", "native scan gate remains mandatory"):
      self.assertIn(expected, test)
    project = PROJECT.read_text(encoding="utf-8")
    self.assertEqual(project.count("path = FirstRunInstallationHealth.swift;"), 1)
    self.assertIn("B98200000000000000000001,", project)
    self.assertIn("B98200000000000000000002,", project)
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("tests/general/first-run-installation-health.py -v", ci)
    self.assertIn("test-first-run-installation-health.swift", ci)
    self.assertIn("TestFirstRunInstallationHealth", ci)
    docs = (ROOT / "docs/first-run-welcome.md").read_text(encoding="utf-8")
    self.assertIn("Basic installation health check (opener-0982)", docs)


if __name__ == "__main__":
  unittest.main()
