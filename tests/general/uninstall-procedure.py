#!/usr/bin/env python3
"""Guard the safe, user-directed uninstall procedure without touching user state."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/uninstall-procedure.md"
CI = ROOT / ".github/workflows/ci.yml"


class UninstallProcedureTests(unittest.TestCase):
  def test_step_order_and_real_entry_points(self):
    text = GUIDE.read_text(encoding="utf-8")
    phases = (
      "## 1. Inspect and back up",
      "## 2. Restore a non-PDF-Magic default",
      "## 3. Restore or disconnect the Finder Quick Action",
      "## 4. Remove only previously approved native messaging registrations",
      "## 5. Retire the managed signature updater",
      "## 6. Remove the verified application",
      "## 7. Verify and retain a recovery path",
    )
    for before, after in zip(phases, phases[1:]):
      self.assertLess(text.index(before), text.index(after))
    for path in (
      "signature_update_launchagent.py",
      "restore_finder_quick_action.py",
      "native-messaging/unregister-hosts.py",
      "native-messaging/uninstall-registration.md",
      "pdf-handler-history",
      "repair-installation.md",
    ):
      with self.subTest(path=path):
        self.assertIn(path, text)
    for path in ("signature_update_launchagent.py",
                 "restore_finder_quick_action.py",
                 "native-messaging/unregister-hosts.py",
                 "native-messaging/uninstall-registration.md",
                 "docs/repair-installation.md"):
      self.assertTrue((ROOT / path).is_file(), path)

  def test_privacy_scanner_defaults_and_unsafe_delete_guardrails(self):
    text = GUIDE.read_text(encoding="utf-8")
    for expected in (
      "do not delete the directory wholesale",
      "do not run these steps with",
      "current macOS PDF handler",
      "no longer the macOS default",
      "may not perform PDF Magic's malware scans",
      "unrecognized or unsafe",
      "byte-for-byte known manifest",
      "launchctl bootout",
      "only verified, unchanged PDF Magic-installed entry points",
      "target-app.txt",
      "freshclam.conf",
      "signatures/",
      "Never recursively erase",
      "No guaranteed malware safety",
      "Stop",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected.lower(), text.lower())
    for forbidden in ("rm -rf", "rm -fr", "sudo rm", "brew uninstall clamav -y",
                      "LSRegisterURL", "defaults delete"):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, text)
    self.assertIn("No uninstall commands or OS mutations run during CI.", text)

  def test_underlying_helpers_are_existing_safety_checked_actions(self):
    settings = (ROOT / "PDFMagicOpenerApp/PDFDefaultApplicationSettingsView.swift").read_text(encoding="utf-8")
    finder = (ROOT / "restore_finder_quick_action.py").read_text(encoding="utf-8")
    hosts = (ROOT / "native-messaging/unregister-hosts.py").read_text(encoding="utf-8")
    agent = (ROOT / "signature_update_launchagent.py").read_text(encoding="utf-8")
    self.assertIn("Restore Previous Default", settings)
    self.assertIn("PDFPreviousDefaultRestoreAction.request(", settings)
    self.assertIn("def restore_finder_action(", finder)
    self.assertIn("RestorationRefused", finder)
    self.assertIn('parser.add_argument("--restore"', finder)
    self.assertIn("def unregister(", hosts)
    self.assertIn("Refusing to remove modified native host registration", hosts)
    self.assertIn("os.O_NOFOLLOW", hosts)
    self.assertIn("detect_existing_signature_update_agent", agent)
    self.assertIn("Existing LaunchAgent does not match the updater identity", agent)
    self.assertIn("os.O_NOFOLLOW", agent)

  def test_ci_executes_procedure_checks(self):
    workflow = CI.read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/general/uninstall-procedure.py -v", workflow)
    self.assertIn("scanner-tests:", workflow)


if __name__ == "__main__":
  unittest.main()
