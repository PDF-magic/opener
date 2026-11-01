#!/usr/bin/env python3
"""Release ZIP packaging invariants with synthetic app content only."""
import importlib.util
import os
from pathlib import Path
import plistlib
import shutil
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
import sys
sys.path.insert(0, str(SCRIPTS))
import package_application_helpers as helpers  # noqa: E402

spec = importlib.util.spec_from_file_location(
  "create_release_archive", SCRIPTS / "create_release_archive.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ReleaseArchiveTests(unittest.TestCase):
  def setUp(self):
    directory = tempfile.TemporaryDirectory()
    self.addCleanup(directory.cleanup)
    self.root = Path(directory.name)
    self.app = self.root / helpers.APP_NAME
    exe = self.app / "Contents/MacOS/PDFMagicOpener"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"\xcf\xfa\xed\xfeapp")
    exe.chmod(0o755)
    with (self.app / "Contents/Info.plist").open("wb") as stream:
      plistlib.dump({
        "CFBundleIdentifier": helpers.BUNDLE_ID,
        "CFBundlePackageType": "APPL",
        "CFBundleExecutable": "PDFMagicOpener",
        "LSUIElement": False,
      }, stream)
    for name in helpers.HELPER_NAMES:
      executable = self.app / helpers.HELPER_FOLDER / name
      executable.parent.mkdir(parents=True, exist_ok=True)
      executable.write_bytes(b"\xcf\xfa\xed\xfehelper")
      executable.chmod(0o755)
    self.zip = self.root / "PDFMagicOpener-unsigned.zip"

  def fake_ditto(self, command, **kwargs):
    self.assertEqual(command[:5], [
      "/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent"])
    self.assertEqual(kwargs["check"], True)
    with zipfile.ZipFile(command[-1], "w", zipfile.ZIP_DEFLATED) as package:
      for path in self.app.rglob("*"):
        package.write(path, arcname=(Path(helpers.APP_NAME) / path.relative_to(self.app)).as_posix())

  def test_creates_and_verifies_an_isolated_zip_without_mutation(self):
    with patch.object(archive.subprocess, "run", side_effect=self.fake_ditto):
      self.assertEqual(archive.create_archive(self.app, self.zip), self.zip)
    self.assertTrue(self.zip.is_file())
    self.assertGreaterEqual(archive.verify_archive(self.zip), len(archive.REQUIRED))
    self.assertFalse((self.app / "Contents/_CodeSignature").exists())
    self.assertEqual(len(helpers.validate_helpers(self.app)), len(helpers.HELPER_NAMES))
    with self.assertRaisesRegex(ValueError, "new .zip"):
      archive.create_archive(self.app, self.zip)

  def test_rejects_missing_helpers_and_unsafe_resources_before_archiving(self):
    (self.app / helpers.HELPER_FOLDER / "launch-scanned-file").unlink()
    with patch.object(archive.subprocess, "run") as run:
      with self.assertRaises(ValueError):
        archive.create_archive(self.app, self.zip)
      run.assert_not_called()
    self.assertFalse(self.zip.exists())
    target = self.app / "Contents/Resources/private.pem"
    target.parent.mkdir(parents=True)
    target.write_text("synthetic marker", encoding="utf-8")
    with self.assertRaisesRegex(ValueError, "Non-distributable"):
      archive.create_archive(self.app, self.zip)

  def write_zip(self, files):
    with zipfile.ZipFile(self.zip, "w") as result:
      for name, content in files.items():
        result.writestr(name, content)

  def test_rejects_traversal_extra_roots_and_sensitive_files(self):
    for bad in (
      "../outside", "unexpected.txt", "PDFMagicOpener.app/Contents/secret.key",
      "PDFMagicOpener.app/Contents/tests/sample", "PDFMagicOpener.app/../../escape",
      "__MACOSX/unexpected/._file",
    ):
      with self.subTest(path=bad):
        self.write_zip({**dict.fromkeys(archive.REQUIRED, b"test"), bad: b"payload"})
        with self.assertRaises(ValueError):
          archive.verify_archive(self.zip)

  def test_rejects_missing_manifest_and_duplicate_files(self):
    self.write_zip({f"{helpers.APP_NAME}/Contents/Info.plist": b"plist"})
    with self.assertRaisesRegex(ValueError, "Missing required"):
      archive.verify_archive(self.zip)
    with zipfile.ZipFile(self.zip, "w") as result:
      for name in archive.REQUIRED:
        result.writestr(name, b"one")
      result.writestr(next(iter(archive.REQUIRED)), b"duplicate")
    with self.assertRaisesRegex(ValueError, "Duplicate"):
      archive.verify_archive(self.zip)

  def test_rejects_symlink_escape_but_accepts_contained_link(self):
    name = f"{helpers.APP_NAME}/Contents/Helpers/link"
    info = zipfile.ZipInfo(name)
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(self.zip, "w") as result:
      for filename in archive.REQUIRED:
        result.writestr(filename, b"test")
      result.writestr(info, b"../../../../etc/passwd")
    with self.assertRaisesRegex(ValueError, "escapes"):
      archive.verify_archive(self.zip)
    with zipfile.ZipFile(self.zip, "w") as result:
      for filename in archive.REQUIRED:
        result.writestr(filename, b"test")
      result.writestr(info, b"launch-scanned-file")
    archive.verify_archive(self.zip)

  def test_ci_exercises_real_macos_archive_and_portable_regressions(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    audit = (ROOT / ".github/workflows/distribution-readiness.yml").read_text(
      encoding="utf-8")
    self.assertIn("scripts/create_release_archive.py --app", ci)
    self.assertIn("scripts/create_release_archive.py --verify", ci)
    self.assertIn("ditto -x -k", ci)
    self.assertIn("tests/general/release-archive.py -v", audit)


if __name__ == "__main__":
  unittest.main()
