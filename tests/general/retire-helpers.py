#!/usr/bin/env python3
"""Disposable native-helper removal regressions; never use a real user home."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
  "retire_installed_helpers", ROOT / "scripts/retire_installed_helpers.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class NativeHelperUninstallTests(unittest.TestCase):
  def setUp(self):
    tmp = tempfile.TemporaryDirectory(prefix="opener-0992-")
    self.addCleanup(tmp.cleanup)
    self.home = Path(tmp.name)
    self.install = self.home / "Library/Application Support/Studio/allow-and-open"
    self.install.mkdir(parents=True)
    self.data = b"\xcf\xfa\xed\xfe" + b"PDF Magic owned native executable"
    for name in mod.HELPERS:
      path = self.install / name
      path.write_bytes(self.data + name.encode())
      path.chmod(0o755)
    self.personal = self.install / "target-app.txt"
    self.personal.write_text("com.example.userviewer\n")
    (self.install / "freshclam.conf").write_text("User custom mirror")
    (self.install / "scan-and-open.py").write_text("customized scanner")
    (self.install / "signatures").mkdir()
    (self.install / "signatures" / "user-signatures").write_bytes(b"keep")
    self.agent = self.home / "Library/LaunchAgents"
    self.agent.mkdir()
    (self.agent / "org.example.other.plist").write_text("unrelated")

  def record(self):
    self.assertIn("ten verified", mod.record_installed_helpers(self.home))
    self.assertEqual((self.install / mod.RECORD).stat().st_mode & 0o777, 0o600)

  def test_inspection_has_no_side_effects(self):
    self.record()
    self.assertIn("10 verified", mod.inspect_installed_helpers(self.home))
    self.assertEqual(len([p for p in self.install.iterdir() if p.name in mod.HELPERS]), 10)

  def test_remove_only_recorded_unchanged_binaries_and_idempotence(self):
    self.record()
    self.assertIn("Removed 10", mod.inspect_installed_helpers(self.home, remove=True))
    self.assertIn("Removed 0", mod.inspect_installed_helpers(self.home, remove=True))
    self.assertTrue((self.install / mod.RECORD).is_file())
    for name in mod.HELPERS:
      self.assertFalse((self.install / name).exists())
    self.assertEqual(self.personal.read_text(), "com.example.userviewer\n")
    self.assertEqual((self.install / "freshclam.conf").read_text(), "User custom mirror")
    self.assertEqual((self.install / "scan-and-open.py").read_text(), "customized scanner")
    self.assertTrue((self.install / "signatures/user-signatures").is_file())
    self.assertTrue((self.agent / "org.example.other.plist").is_file())

  def test_missing_or_untracked_record_never_removes_an_executable(self):
    with self.assertRaises(mod.HelperRemovalRefused):
      mod.inspect_installed_helpers(self.home, remove=True)
    self.assertTrue((self.install / mod.HELPERS[0]).is_file())
    self.record()
    (self.install / mod.RECORD).unlink()
    with self.assertRaises(mod.HelperRemovalRefused):
      mod.inspect_installed_helpers(self.home, remove=True)

  def test_modified_target_fails_preflight_without_partial_delete(self):
    self.record()
    (self.install / mod.HELPERS[-1]).write_bytes(self.data + b"user modification")
    with self.assertRaises(mod.HelperRemovalRefused):
      mod.inspect_installed_helpers(self.home, remove=True)
    self.assertTrue(all((self.install / name).is_file() for name in mod.HELPERS))

  def test_unsafe_symlink_hardlink_directory_and_substituted_record_refused(self):
    for issue in ("symlink", "hardlink", "folder", "manifest-symlink", "manifest-mode"):
      with self.subTest(issue=issue):
        path = self.install / mod.HELPERS[0]
        path.unlink(missing_ok=True)
        path.write_bytes(self.data + mod.HELPERS[0].encode())
        path.chmod(0o755)
        self.record()
        alias = self.install / "alias"
        alias.unlink(missing_ok=True)
        marker = self.install / mod.RECORD
        if issue == "symlink":
          path.unlink()
          path.symlink_to(self.personal)
        elif issue == "hardlink":
          os.link(path, alias)
        elif issue == "folder":
          path.unlink()
          path.mkdir()
        elif issue == "manifest-symlink":
          marker.unlink()
          marker.symlink_to(self.personal)
        elif issue == "manifest-mode":
          marker.chmod(0o644)
        with self.assertRaises((mod.HelperRemovalRefused, OSError)):
          mod.inspect_installed_helpers(self.home, remove=True)
        self.assertEqual(self.personal.read_text(), "com.example.userviewer\n")
        self.assertTrue((self.install / mod.HELPERS[1]).exists())
        if issue == "folder":
          path.rmdir()
        elif issue == "symlink":
          path.unlink()
        elif issue == "hardlink":
          alias.unlink()
        if issue == "manifest-symlink":
          marker.unlink()
        elif issue == "manifest-mode":
          marker.chmod(0o600)

  def test_record_rejects_invalid_binary_and_bad_manifest(self):
    first = self.install / mod.HELPERS[0]
    first.write_bytes(b"not a Mach-O executable")
    with self.assertRaises(mod.HelperRemovalRefused):
      mod.record_installed_helpers(self.home)
    self.assertFalse((self.install / mod.RECORD).exists())
    first.write_bytes(self.data + mod.HELPERS[0].encode())
    self.record()
    marker = self.install / mod.RECORD
    marker.write_text(json.dumps({"version": 1, "helpers": {"surprise": "0" * 64}}))
    with self.assertRaises(mod.HelperRemovalRefused):
      mod.record_installed_helpers(self.home)

  def test_symlinked_support_ancestor_never_traversed(self):
    self.record()
    support = self.home / "Library/Application Support"
    moved = self.home / "saved-support"
    support.rename(moved)
    support.symlink_to(moved)
    with self.assertRaises(mod.HelperRemovalRefused):
      mod.inspect_installed_helpers(self.home, remove=True)
    self.assertTrue((moved / "Studio/allow-and-open" / mod.HELPERS[0]).exists())

  def test_root_rejected_without_changes(self):
    self.record()
    with patch.object(mod.os, "geteuid", return_value=0), \
         self.assertRaises(SystemExit) as caught:
      mod.main(["--remove"])
    self.assertEqual(caught.exception.code, 1)
    self.assertTrue((self.install / mod.HELPERS[0]).exists())

  def test_ci_guide_installer_and_rollback_integration(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    installer = (ROOT / "install-allow-and-open.sh").read_text()
    recovery = (ROOT / "scripts/preserve_existing_opener.py").read_text()
    guide = (ROOT / "docs/uninstall-procedure.md").read_text()
    self.assertIn("tests/general/retire-helpers.py -v", ci)
    self.assertIn('retire_installed_helpers.py" --record-install', installer)
    self.assertIn('".pdf-magic-native-helpers.json"', recovery)
    self.assertIn("python3 scripts/retire_installed_helpers.py --remove", guide)
    self.assertIn("already disconnected", guide)
    self.assertNotIn("rm -rf", guide)
    self.assertNotIn("shutil.rmtree", (ROOT / "scripts/retire_installed_helpers.py").read_text())


if __name__ == "__main__":
  unittest.main()
