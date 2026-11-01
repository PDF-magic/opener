#!/usr/bin/env python3
"""Guard the safe, user-directed uninstall procedure without touching user state."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import os
from io import StringIO
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/uninstall-procedure.md"
CI = ROOT / ".github/workflows/ci.yml"
STATUS_SOURCE = ROOT / "pdf-handler-status.py"
STATUS_COMMAND = (
  'python3 "$HOME/Library/Application Support/Studio/allow-and-open/pdf-handler-status.py"'
)


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


  def test_pdf_handler_lookup_is_required_before_removal_and_repeated(self):
    guide = GUIDE.read_text(encoding="utf-8")
    self.assertEqual(guide.count(STATUS_COMMAND), 2)
    self.assertLess(guide.index(STATUS_COMMAND), guide.index("## 2. Restore"))
    self.assertLess(guide.rindex(STATUS_COMMAND), guide.index("## 3. Restore"))
    self.assertLess(guide.rindex(STATUS_COMMAND), guide.index("## 6. Remove"))
    for requirement in (
      "Current macOS PDF handler",
      "PDF Magic Opener is the default PDF handler",
      "PDF Magic Opener is not the default PDF handler",
      "stop uninstallation",
      "stop before removing the app or its helpers",
      "known non-PDF-Magic default",
      "another application is already the default",
      "preserve that choice",
    ):
      with self.subTest(requirement=requirement):
        self.assertIn(requirement.lower(), guide.lower())

  def test_uninstall_status_reports_exact_current_handler_or_fails_closed(self):
    # Run the real read-only status CLI against fake native-helper responses.
    # No macOS associations, installed binaries or real user data are touched.
    spec = importlib.util.spec_from_file_location("uninstall_status_check", STATUS_SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for output, expected_status in (
      (b"local.studio.brave-pdf-opener\n", "PDF Magic Opener is the default PDF handler."),
      (b"com.apple.Preview\n", "PDF Magic Opener is not the default PDF handler."),
      (b"com.adobe.Reader\n", "PDF Magic Opener is not the default PDF handler."),
    ):
      with self.subTest(output=output):
        captured, errors = StringIO(), StringIO()
        fake = subprocess.CompletedProcess(["identify-pdf-handler"], 0, output, b"")
        with patch.object(module.subprocess, "run", return_value=fake) as run, \
             redirect_stdout(captured), redirect_stderr(errors):
          result = module.main([])
        self.assertEqual(result, 0)
        self.assertIn(expected_status, captured.getvalue())
        self.assertEqual(errors.getvalue(), "")
        run.assert_called_once_with(
          [str(module.HANDLER_LOOKUP)], capture_output=True, check=True, timeout=10
        )
    for output in (b"", b"com..wrong\n", b"com.apple.Preview\nother\n", b"\xff\n"):
      with self.subTest(output=output):
        captured, errors = StringIO(), StringIO()
        fake = subprocess.CompletedProcess(["identify-pdf-handler"], 0, output, b"")
        with patch.object(module.subprocess, "run", return_value=fake), \
             redirect_stdout(captured), redirect_stderr(errors):
          result = module.main([])
        self.assertEqual(result, 1)
        self.assertEqual(captured.getvalue(), "")
        self.assertEqual(errors.getvalue().strip(), module.LOOKUP_ERROR)
    with patch.object(module.subprocess, "run", side_effect=FileNotFoundError()), \
         redirect_stdout(StringIO()) as captured, redirect_stderr(StringIO()) as errors:
      self.assertEqual(module.main([]), 1)
    self.assertEqual(captured.getvalue(), "")
    self.assertEqual(errors.getvalue().strip(), module.LOOKUP_ERROR)
    source = STATUS_SOURCE.read_text(encoding="utf-8")
    for forbidden in ("LSSetDefault", "setDefaultApplication", "target-app.txt", "UserDefaults",
                      "os.unlink", "os.remove", "shutil.rmtree"):
      self.assertNotIn(forbidden, source)

  def test_preference_retention_prompt_precedes_removal(self):
    guide = GUIDE.read_text(encoding="utf-8")
    helper = ROOT / "ask_uninstall_preferences.py"
    self.assertTrue(helper.is_file())
    question = "Ask whether PDF Magic Opener preferences should be retained"
    self.assertIn(question, guide)
    self.assertLess(guide.index("python3 ask_uninstall_preferences.py"),
                    guide.index(STATUS_COMMAND))
    self.assertLess(guide.index("python3 ask_uninstall_preferences.py"),
                    guide.index("## 2. Restore"))
    for requirement in (
      "default when pressing Enter",
      "**No** answer is not blanket authorization",
      "not an automated preference-deletion step",
      "local.studio.pdf-magic-opener.plist",
    ):
      self.assertIn(requirement, guide)

  def test_retention_prompt_choices_do_not_change_user_files(self):
    helper = ROOT / "ask_uninstall_preferences.py"
    spec = importlib.util.spec_from_file_location("retention_prompt_test", helper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with TemporaryDirectory() as folder:
      home = Path(folder)
      prefs = home / "Library/Preferences/local.studio.pdf-magic-opener.plist"
      scanner = home / "Library/Application Support/Studio/allow-and-open/target-app.txt"
      for path, data in ((prefs, b"custom preference"), (scanner, b"selected browser")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
      for answer, expected in (
        ("", "Decision: RETAIN"),
        ("y", "Decision: RETAIN"),
        ("YES", "Decision: RETAIN"),
        ("n", "Decision: DO NOT RETAIN"),
        ("No", "Decision: DO NOT RETAIN"),
      ):
        with self.subTest(answer=answer):
          out, err = StringIO(), StringIO()
          with patch.dict(os.environ, {"HOME": str(home)}), \
               patch("builtins.input", return_value=answer) as prompt, \
               redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(module.main([]), 0)
          prompt.assert_called_once_with(module.PROMPT)
          self.assertIn(expected, out.getvalue())
          self.assertEqual(err.getvalue(), "")
          self.assertEqual(prefs.read_bytes(), b"custom preference")
          self.assertEqual(scanner.read_bytes(), b"selected browser")
      for bad in ("maybe", EOFError(), KeyboardInterrupt()):
        with self.subTest(bad=str(bad)):
          out, err = StringIO(), StringIO()
          with patch("builtins.input", side_effect=bad if isinstance(bad, BaseException) else None,
                     return_value=bad if isinstance(bad, str) else None), \
               redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(module.main([]), 1)
          self.assertIn("No retention decision recorded" if not isinstance(bad, str)
                        else "Invalid answer", err.getvalue())
          self.assertEqual(prefs.read_bytes(), b"custom preference")
          self.assertEqual(scanner.read_bytes(), b"selected browser")
      result = subprocess.run(
        [sys.executable, str(helper)],
        input="no\n", text=True, capture_output=True, check=False,
        env={**os.environ, "HOME": str(home)},
      )
      self.assertEqual(result.returncode, 0, result.stderr)
      self.assertIn("Decision: DO NOT RETAIN", result.stdout)
      self.assertEqual(prefs.read_bytes(), b"custom preference")
      self.assertEqual(scanner.read_bytes(), b"selected browser")

  def test_ci_executes_procedure_checks(self):
    workflow = CI.read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/general/uninstall-procedure.py -v", workflow)
    self.assertIn("scanner-tests:", workflow)


if __name__ == "__main__":
  unittest.main()
