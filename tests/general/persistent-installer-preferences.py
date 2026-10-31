#!/usr/bin/env python3
"""Exercise the installer's existing preference initializer without installing anything."""

from pathlib import Path
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


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
    freshclam = re.search(
      r"python3 - \"\\$install_dir\" <<'CONFIG'\\n(.*?)\\nCONFIG",
      installer, re.DOTALL,
    )
    agent = re.search(
      r"python3 - \"\\$app\" \"\\$install_dir\" \"\\$app_name\" <<'CONFIG'\\n(.*?)\\nCONFIG",
      installer, re.DOTALL,
    )
    if not freshclam or not agent:
      raise AssertionError("Installer migration initializers not found")
    cls.freshclam_initializer = freshclam.group(1)
    cls.agent_initializer = agent.group(1)

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


  def run_initializer(self, initializer, *args, home=None):
    env = os.environ.copy()
    if home is not None:
      env["HOME"] = str(home)
    return subprocess.run(
      [sys.executable, "-c", initializer, *map(str, args)],
      env=env, capture_output=True, text=True,
    )

  def test_new_install_creates_private_freshclam_configuration(self):
    with tempfile.TemporaryDirectory() as directory:
      install = Path(directory) / "install"
      install.mkdir()
      (install / "signatures").mkdir()
      result = self.run_initializer(self.freshclam_initializer, install)
      self.assertEqual(result.returncode, 0, result.stderr)
      config = install / "freshclam.conf"
      self.assertIn(b"DatabaseMirror database.clamav.net", config.read_bytes())
      self.assertIn(str(install / "signatures").encode(), config.read_bytes())
      self.assertEqual(config.stat().st_mode & 0o777, 0o600)

  def test_upgrade_preserves_freshclam_customizations_exactly(self):
    with tempfile.TemporaryDirectory() as directory:
      install = Path(directory) / "install"
      install.mkdir()
      config = install / "freshclam.conf"
      custom = b"DatabaseMirror mirror.example.org\\nScriptedUpdates no\\n# custom\\n"
      config.write_bytes(custom)
      original = config.stat()
      for _ in range(2):
        result = self.run_initializer(self.freshclam_initializer, install)
        self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(config.read_bytes(), custom)
      self.assertEqual(config.stat().st_ino, original.st_ino)
      self.assertEqual(config.stat().st_mtime_ns, original.st_mtime_ns)

  def test_unsafe_freshclam_configuration_is_not_followed(self):
    with tempfile.TemporaryDirectory() as directory:
      install = Path(directory) / "install"
      install.mkdir()
      target = Path(directory) / "unrelated"
      target.write_bytes(b"unmodified")
      config = install / "freshclam.conf"
      config.symlink_to(target)
      result = self.run_initializer(self.freshclam_initializer, install)
      self.assertNotEqual(result.returncode, 0)
      self.assertTrue(config.is_symlink())
      self.assertEqual(target.read_bytes(), b"unmodified")
      config.unlink()
      config.mkdir()
      result = self.run_initializer(self.freshclam_initializer, install)
      self.assertNotEqual(result.returncode, 0)
      self.assertTrue(config.is_dir())

  def test_existing_launch_agent_schedule_is_not_rewritten(self):
    import plistlib
    with tempfile.TemporaryDirectory() as directory:
      home = Path(directory) / "home"
      agents = home / "Library/LaunchAgents"
      agents.mkdir(parents=True)
      install = home / "Library/Application Support/Studio/allow-and-open"
      install.mkdir(parents=True)
      app = Path(directory) / "staged.app"
      (app / "Contents").mkdir(parents=True)
      first = self.run_initializer(
        self.agent_initializer, app, install, "PDF Magic Opener", home=home,
      )
      self.assertEqual(first.returncode, 0, first.stderr)
      agent = agents / "local.studio.pdf-malware-signatures.plist"
      self.assertEqual(agent.stat().st_mode & 0o777, 0o600)
      settings = plistlib.loads(agent.read_bytes())
      self.assertEqual(settings["StartInterval"], 14400)
      settings["StartInterval"] = 7200
      settings["RunAtLoad"] = False
      custom = plistlib.dumps(settings)
      agent.write_bytes(custom)
      original = agent.stat()
      for _ in range(2):
        result = self.run_initializer(
          self.agent_initializer, app, install, "PDF Magic Opener", home=home,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
      self.assertEqual(agent.read_bytes(), custom)
      self.assertEqual(agent.stat().st_ino, original.st_ino)
      self.assertEqual(agent.stat().st_mtime_ns, original.st_mtime_ns)

  def test_existing_launch_agent_symlink_is_rejected(self):
    with tempfile.TemporaryDirectory() as directory:
      home = Path(directory) / "home"
      agents = home / "Library/LaunchAgents"
      agents.mkdir(parents=True)
      install = Path(directory) / "install"
      install.mkdir()
      app = Path(directory) / "staged.app"
      (app / "Contents").mkdir(parents=True)
      target = Path(directory) / "unrelated"
      target.write_bytes(b"unmodified")
      agent = agents / "local.studio.pdf-malware-signatures.plist"
      agent.symlink_to(target)
      result = self.run_initializer(
        self.agent_initializer, app, install, "PDF Magic Opener", home=home,
      )
      self.assertNotEqual(result.returncode, 0)
      self.assertTrue(agent.is_symlink())
      self.assertEqual(target.read_bytes(), b"unmodified")


if __name__ == "__main__":
  unittest.main()
