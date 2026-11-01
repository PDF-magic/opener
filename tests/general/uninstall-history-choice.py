#!/usr/bin/env python3
"""Verify the guided uninstall retention question never alters history."""

import importlib.util
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
CHOICE = ROOT / "ask_scan_history_retention.py"
GUIDE = ROOT / "docs/uninstall-procedure.md"
CI = ROOT / ".github/workflows/ci.yml"


class UninstallHistoryChoiceTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    spec = importlib.util.spec_from_file_location("uninstall_history_choice", CHOICE)
    cls.helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cls.helper)

  def run_choice(self, answer):
    stdout, stderr = StringIO(), StringIO()
    with patch("builtins.open", side_effect=AssertionError("must not open files")), \
         patch("subprocess.run", side_effect=AssertionError("must not run commands")):
      status = self.helper.main(stdin=StringIO(answer), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()

  def test_explicit_yes_and_safe_blank_default_preserve_history(self):
    for answer in ("yes\n", "Y\n", "\n"):
      with self.subTest(answer=answer):
        status, output, errors = self.run_choice(answer)
        self.assertEqual(status, 0)
        self.assertIn("Keep scan history", output)
        self.assertNotIn("Do not retain scan history", output)
        self.assertEqual(errors, "")

  def test_no_only_gives_existing_confirmed_clear_history_path(self):
    for answer in ("n\n", "NO\n"):
      with self.subTest(answer=answer):
        status, output, errors = self.run_choice(answer)
        self.assertEqual(status, 0)
        self.assertIn("no data has been deleted", output)
        self.assertIn("Clear History…", output)
        self.assertIn("stop; do not delete files manually", output)
        self.assertEqual(errors, "")

  def test_cancel_eof_and_input_error_fail_closed(self):
    for answer in ("cancel\n", "q\n", ""):
      with self.subTest(answer=answer):
        status, output, errors = self.run_choice(answer)
        self.assertEqual(status, 1)
        self.assertTrue("unchanged" in output or "preserve" in errors)
    class UnreadableInput:
      def readline(self):
        raise OSError("test input failure")
    self.assertEqual(self.helper.main(stdin=UnreadableInput(),
                                      stdout=StringIO(), stderr=StringIO()), 1)

  def test_invalid_answer_requires_a_new_explicit_choice(self):
    status, output, errors = self.run_choice("maybe\nno\n")
    self.assertEqual(status, 0)
    self.assertIn("Enter yes, no, or cancel", output)
    self.assertIn("Do not retain scan history", output)
    self.assertEqual(errors, "")

  def test_guided_uninstall_asks_before_removing_app(self):
    guide = GUIDE.read_text(encoding="utf-8")
    self.assertIn("python3 ask_scan_history_retention.py", guide)
    self.assertLess(guide.index("python3 ask_scan_history_retention.py"),
                    guide.index("## 2. Restore"))
    self.assertIn("Clear History…", guide)
    self.assertIn("Stop uninstallation", guide)
    self.assertIn("never deletes history", guide)
    self.assertIn("retain scan history", guide.lower())
    self.assertIn("never recursively erase", guide.lower())
    self.assertIn("tests/general/uninstall-history-choice.py -v",
                  CI.read_text(encoding="utf-8"))

  def test_helper_contains_no_storage_or_process_mutations(self):
    code = CHOICE.read_text(encoding="utf-8")
    for forbidden in ("unlink(", "remove(", "rmtree(", "sqlite3", "subprocess", "os.system(",
                      "Path(", "open(", "write_text(", "UserDefaults"):
      self.assertNotIn(forbidden, code)


if __name__ == "__main__":
  unittest.main()
