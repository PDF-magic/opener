#!/usr/bin/env python3
"""No unrelated or customized application is authorized for uninstall."""
import importlib.util
import os
from pathlib import Path
import plistlib
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_pdf_opener_bundle import METADATA

spec = importlib.util.spec_from_file_location(
  "verify_uninstall_app", ROOT / "scripts/verify_uninstall_app.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


class UninstallOwnershipTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory(prefix="opener-uninstall-owner-")
    self.addCleanup(temp.cleanup)
    self.home = Path(temp.name) / "home"
    self.apps = self.home / "Applications"
    self.apps.mkdir(parents=True)
    self.app = self.apps / check.APP_NAME
    self.other = self.apps / "An Unrelated PDF App.app"
    self.other.mkdir()
    (self.other / "important.txt").write_bytes(b"other app")
    self.app.mkdir()
    files = {
      "Contents/Info.plist": plistlib.dumps(METADATA),
      "Contents/MacOS/PDFOpener": b"native scan executable",
      "Contents/MacOS/MakePDFMagicDefault": b"handler helper",
      "Contents/Resources/twilight-reading.png": b"\x89PNG\r\n\x1a\nimage",
    }
    for name, content in files.items():
      file = self.app / name
      file.parent.mkdir(parents=True, exist_ok=True)
      file.write_bytes(content)
      file.chmod(0o755 if "/MacOS/" in name else 0o644)

  def verify(self, **kwargs):
    return check.verify_installed_app(self.home, **kwargs)

  def assert_unrelated_untouched(self):
    self.assertEqual((self.other / "important.txt").read_bytes(), b"other app")

  def test_exact_owned_bundle_is_read_only_and_other_apps_survive(self):
    before = {p.relative_to(self.home): p.read_bytes()
              for p in self.home.rglob("*") if p.is_file()}
    self.assertTrue(self.verify())
    self.assertEqual(before, {p.relative_to(self.home): p.read_bytes()
                              for p in self.home.rglob("*") if p.is_file()})
    self.assert_unrelated_untouched()

  def test_absent_app_is_noop_even_with_other_apps_present(self):
    self.app.rename(self.apps / "A Renamed App.app")
    self.assertFalse(self.verify())
    self.assertTrue((self.apps / "A Renamed App.app").is_dir())
    self.assert_unrelated_untouched()

  def test_wrong_bundle_identity_is_refused(self):
    info = self.app / "Contents/Info.plist"
    altered = dict(METADATA, CFBundleIdentifier="com.other.vendor")
    info.write_bytes(plistlib.dumps(altered))
    with self.assertRaisesRegex(ValueError, "Unexpected app identity"):
      self.verify()
    self.assertTrue(info.is_file())
    self.assert_unrelated_untouched()

  def test_unrecognized_customization_is_not_automatically_deleted(self):
    extra = self.app / "Contents/Resources/user-settings"
    extra.write_text("important custom data")
    with self.assertRaisesRegex(ValueError, "Unexpected app file"):
      self.verify()
    self.assertEqual(extra.read_text(), "important custom data")
    self.assert_unrelated_untouched()

  def test_symlinked_app_and_parent_do_not_qualify(self):
    outside = self.home / "outside"
    self.app.rename(outside)
    self.app.symlink_to(outside, target_is_directory=True)
    with self.assertRaises(ValueError):
      self.verify()
    self.assertTrue((outside / "Contents/Info.plist").is_file())
    self.app.unlink()
    self.apps.rename(self.home / "real-applications")
    self.apps.symlink_to(self.home / "real-applications", target_is_directory=True)
    with self.assertRaises(ValueError):
      self.verify()
    self.assert_unrelated_untouched()

  def test_unowned_home_bundle_and_hardlinked_executable_refused(self):
    with self.assertRaisesRegex(ValueError, "unowned"):
      self.verify(uid=os.getuid() + 1)
    executable = self.app / "Contents/MacOS/PDFOpener"
    outside = self.home / "other-executable"
    os.link(executable, outside)
    with self.assertRaisesRegex(ValueError, "multiply linked"):
      self.verify()
    self.assertEqual(outside.read_bytes(), b"native scan executable")
    self.assert_unrelated_untouched()

  def test_no_broad_removal_and_documented_ci_gate(self):
    source = (ROOT / "scripts/verify_uninstall_app.py").read_text()
    for forbidden in ("unlink(", "rmtree(", "shutil.move(", "os.remove(", "rm -rf"):
      self.assertNotIn(forbidden, source)
    guide = (ROOT / "docs/uninstall-procedure.md").read_text()
    self.assertIn("python3 scripts/verify_uninstall_app.py", guide)
    self.assertIn("read-only", guide.lower())
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 tests/general/uninstall-app-ownership.py -v", ci)


if __name__ == "__main__":
  unittest.main()
