#!/usr/bin/env python3
"""Verify explicit, confirmed restore-previous-default UI and native safety gates."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
ACTION = (ROOT / "PDFMagicOpenerApp" / "PDFDefaultApplicationSettingsView.swift").read_text()
GENERAL = (ROOT / "PDFMagicOpenerApp" / "GeneralSettingsView.swift").read_text()
HISTORY = (ROOT / "pdf-handler-history.swift").read_text()
INSTALLER = (ROOT / "install-allow-and-open.sh").read_text()
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()


class RestorePreviousDefaultTests(unittest.TestCase):
  def test_action_is_in_existing_general_section_and_requires_confirmation(self):
    self.assertIn("PDFDefaultApplicationSettingsView()", GENERAL)
    for required in (
        'Button("Restore Previous Default") {',
        'showingRestoreConfirmation = true',
        '.confirmationDialog(',
        'isPresented: $showingRestoreConfirmation',
        'Button("Restore Previous Default", role: .destructive)',
        'Button("Cancel", role: .cancel)',
        'restorePreviousOnUserRequest()',
        'accessibilityIdentifier("restorePreviousDefaultPDFAppButton")',
        'accessibilityIdentifier("restorePreviousDefaultResult")',
        '.disabled(isSettingDefault || isRestoringDefault)',
        'guard !isSettingDefault && !isRestoringDefault else { return }',
        'PDFPreviousDefaultRestoreAction.request(',
    ):
      with self.subTest(required=required):
        self.assertIn(required, ACTION)
    self.assertNotIn("onAppear", ACTION)
    self.assertNotIn("onChange", ACTION)
    self.assertNotIn("task {", ACTION)

  def test_restoration_only_when_scan_handler_is_still_default(self):
    for required in (
        'currentPDFHandler() == PDFDefaultApplicationAction.handlerBundleID',
        'guard success,',
        'let observed = currentPDFHandler()',
        'observed != PDFDefaultApplicationAction.handlerBundleID',
        'completion(false)',
        'completion(true)',
        'restoreResultMessage = success',
    ):
      with self.subTest(required=required):
        self.assertIn(required, ACTION)

  def test_uses_installed_history_tool_not_direct_launch_services(self):
    for required in (
        'historyCommand = "pdf-handler-history"',
        'historyFilename = "previous-pdf-handler.txt"',
        'destinationOfSymbolicLink(atPath: folder.path)',
        'destinationOfSymbolicLink(atPath: helper.path)',
        'helperAttributes',  # replaced below with actual symbol name
        'files.isExecutableFile(atPath: helper.path)',
        'process.executableURL = helper',
        'process.arguments = ["restore", history.path]',
        'finished.terminationStatus == 0',
    ):
      with self.subTest(required=required):
        self.assertIn(required.replace("helperAttributes", "let attributes ="), ACTION)
    self.assertNotIn("target-app.txt", ACTION)
    self.assertNotIn("LSSetDefault", ACTION)
    self.assertNotIn("NSWorkspace.shared.setDefaultApplication", ACTION)
    self.assertNotIn("setDefaultApplication(at:", ACTION)
    self.assertNotIn("/bin/sh", ACTION)

  def test_native_history_fails_closed_for_missing_or_unverified_record(self):
    for required in (
        "O_RDONLY | O_NOFOLLOW | O_CLOEXEC",
        "status.st_mode & mode_t(0o077)",
        "validPreviousPDFBundleIdentifier(identifier)",
        "current == openerPDFBundleIdentifier",
        "bundle.bundleIdentifier == identifier",
        "FileManager.default.isExecutableFile(atPath: executable.path)",
        'case "restore":',
        "readPreviousPDFHandler(at: path)",
        "restorablePDFApplication(",
        "currentDefaultPDFBundleIdentifier() == expected",
    ):
      with self.subTest(required=required):
        self.assertIn(required, HISTORY)
    self.assertIn('"$script_dir/pdf-handler-history.swift"', INSTALLER)
    self.assertIn('"$install_dir/pdf-handler-history"', INSTALLER)
    self.assertIn('"$install_dir/previous-pdf-handler.txt"', INSTALLER)

  def test_regression_suite_exercises_restore_with_no_system_mutations(self):
    self.assertIn("tests/general/restore-previous-default.py -v", CI)
    self.assertIn("test-general-restore-previous-default.swift", CI)
    self.assertIn("PDF_DEFAULT_ACTION_TESTING", CI)
    self.assertIn('Button("Set as Default PDF App")', ACTION)


if __name__ == "__main__":
  unittest.main()
