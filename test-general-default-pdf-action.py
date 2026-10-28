#!/usr/bin/env python3
"""Verify the General settings default PDF action is opt-in and scanner-safe."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp"
GENERAL = APP / "GeneralSettingsView.swift"
ACTION = APP / "PDFDefaultApplicationSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class GeneralDefaultPDFActionTests(unittest.TestCase):
  def test_button_only_appears_in_general_and_requires_a_click(self):
    general = GENERAL.read_text(encoding="utf-8")
    action = ACTION.read_text(encoding="utf-8")
    self.assertIn("PDFDefaultApplicationSettingsView()", general)
    self.assertIn('Button("Set as Default PDF App") {', action)
    self.assertIn("setDefaultOnUserRequest()", action)
    self.assertIn('.accessibilityIdentifier("setDefaultPDFAppButton")', action)
    self.assertIn('.accessibilityIdentifier("defaultPDFApplicationSection")', action)
    self.assertIn('.disabled(isSettingDefault)', action)
    self.assertIn("resultMessage = success", action)
    self.assertNotIn("onAppear", action)
    self.assertNotIn("onChange", action)
    self.assertNotIn("task {", action)

  def test_only_verified_installed_scan_handler_can_be_default(self):
    src = ACTION.read_text(encoding="utf-8")
    for expected in (
        '"local.studio.brave-pdf-opener"',
        '"Applications/PDF Magic Opener.app"',
        '"Contents/MacOS/MakePDFMagicDefault"',
        'bundle.bundleIdentifier == handlerBundleID',
        '"CFBundleDocumentTypes"',
        '"com.adobe.pdf"',
        "files.isExecutableFile(atPath: executable.path)",
        "destinationOfSymbolicLink(atPath: application.path)",
        "destinationOfSymbolicLink(atPath: helper.path)",
        "process.arguments = []",
        "currentPDFHandler() == handlerBundleID",
        'LSCopyDefaultRoleHandlerForContentType(UTType.pdf.identifier as CFString, .all)',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, src)
    self.assertNotIn("local.studio.pdfmagicopener.swiftui", src)
    for forbidden in ("target-app.txt", "/bin/sh", "NSWorkspace.shared.setDefaultApplication",
                      "setDefaultApplication(at:", "UserDefaults", "@AppStorage",
                      "clamscan", "LSSetDefault", "ProcessInfo.processInfo.arguments"):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, src)

  def test_app_target_and_ci_include_protected_action(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn("path = PDFDefaultApplicationSettingsView.swift;", project)
    self.assertIn("fileRef = B19700000000000000000002;", project)
    src = project.split("isa = PBXSourcesBuildPhase;", 1)[1].split(
        "runOnlyForDeploymentPostprocessing", 1)[0]
    self.assertIn("B19700000000000000000001,", src)
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("test-general-default-pdf-action.py -v", ci)
    self.assertIn("test-general-default-pdf-action.swift", ci)
    self.assertIn("PDF_DEFAULT_ACTION_TESTING", ci)


if __name__ == "__main__":
  unittest.main()
