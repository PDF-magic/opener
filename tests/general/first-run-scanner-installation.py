#!/usr/bin/env python3
"""Protect the read-only first-run scanner installation check (opener-0975)."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "PDFMagicOpenerApp/FirstRunScannerInstallation.swift"
WELCOME = ROOT / "PDFMagicOpenerApp/FirstRunWelcomeView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj"
CI = ROOT / ".github/workflows/ci.yml"
GATE = ROOT / "scan-and-open.py"


class FirstRunScannerInstallationTests(unittest.TestCase):
  def test_scanner_discovery_tracks_runtime_fixed_paths(self):
    checker = CHECK.read_text(encoding="utf-8")
    gate = GATE.read_text(encoding="utf-8")
    for location in ("/opt/homebrew/bin/clamscan", "/usr/local/bin/clamscan",
                     "/usr/local/clamav/bin/clamscan"):
      self.assertIn(location, checker)
      self.assertIn(repr(location), gate)
    self.assertIn('appendingPathComponent("freshclam")', checker)
    self.assertIn("isExecutableRegularFile", checker)
    self.assertIn(".typeRegular", checker)
    self.assertIn("resolvingSymlinksInPath()", checker)
    self.assertIn(".updaterMissing", checker)
    self.assertIn(".scannerMissing", checker)

  def test_check_is_diagnostic_and_never_changes_file_opening_or_settings(self):
    checker = CHECK.read_text(encoding="utf-8")
    for forbidden in ("Process(", "subprocess", "NSWorkspace", "LSSetDefault",
                      "UserDefaults", "createFile(", "write(", "removeItem(",
                      "run_scan", "check_database", "openDocument(", "Task {"):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, checker)
    self.assertIn("The installed scan gate independently validates", checker)

  def test_first_run_displays_actual_status_and_allows_recheck(self):
    welcome = WELCOME.read_text(encoding="utf-8")
    self.assertIn("@State private var scannerInstallation", welcome)
    self.assertIn("FirstRunScannerInstallation.check()", welcome)
    self.assertIn('Label("Scanner installation check"', welcome)
    self.assertIn('accessibilityIdentifier("firstRunScannerInstallationStatus")', welcome)
    self.assertIn('Button("Check Scanner Again")', welcome)
    self.assertIn("signature freshness", welcome)
    self.assertIn("does not verify", welcome)
    self.assertIn("if welcomePending", welcome)
    self.assertIn("FirstRunWelcomeState.acknowledge()", welcome)

  def test_native_and_portable_ci_compile_and_execute_the_new_tests(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertEqual(project.count("path = FirstRunScannerInstallation.swift;"), 1)
    self.assertIn("B97500000000000000000001,", project)
    self.assertIn("B97500000000000000000002,", project)
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("tests/general/first-run-scanner-installation.py -v", ci)
    self.assertIn("test-first-run-scanner-installation.swift", ci)
    self.assertIn("TestFirstRunScannerInstallation", ci)


if __name__ == "__main__":
  unittest.main()
