#!/usr/bin/env python3
"""Exercise the installer's existing preference initializer without installing anything."""

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class PersistentInstallerPreferenceTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    match = re.search(
      r"python3 - \"\$install_dir/target-app\.txt\" <<'TARGET_APP'\n(.*?)\nTARGET_APP",
      installer,
      re.DOTALL,
    )
    if not match:
      raise AssertionError("Installer's existing preference initializer not found")
    cls.initializer = match.group(1)

  def initialize(self, path):
    subprocess.run(
      [sys.executable, "-c", self.initializer, str(path)],
      check=True,
      capture_output=True,
      text=True,
    )

  def test_new_install_initializes_only_missing_choice(self):
    with tempfile.TemporaryDirectory() as directory:
      choice = Path(directory) / "target-app.txt"
      self.initialize(choice)
      self.assertEqual(choice.read_text(encoding="ascii"), "com.brave.Browser\n")
      self.assertEqual(choice.stat().st_mode & 0o777, 0o600)
      first_stat = choice.stat()
      self.initialize(choice)
      self.assertEqual(choice.stat().st_ino, first_stat.st_ino)
      self.assertEqual(choice.read_text(encoding="ascii"), "com.brave.Browser\n")

  def test_upgrade_preserves_custom_choice_without_replacing_file(self):
    with tempfile.TemporaryDirectory() as directory:
      choice = Path(directory) / "target-app.txt"
      choice.write_text("org.mozilla.firefox\n", encoding="ascii")
      original = choice.stat()
      for _ in range(2):
        self.initialize(choice)
      self.assertEqual(choice.read_text(encoding="ascii"), "org.mozilla.firefox\n")
      self.assertEqual(choice.stat().st_ino, original.st_ino)
      self.assertEqual(choice.stat().st_mtime_ns, original.st_mtime_ns)

  def test_existing_symlink_is_not_followed_or_replaced(self):
    with tempfile.TemporaryDirectory() as directory:
      target = Path(directory) / "existing.txt"
      target.write_text("com.google.Chrome\n", encoding="ascii")
      choice = Path(directory) / "target-app.txt"
      choice.symlink_to(target)
      self.initialize(choice)
      self.assertTrue(choice.is_symlink())
      self.assertEqual(target.read_text(encoding="ascii"), "com.google.Chrome\n")


if __name__ == "__main__":
  unittest.main()
