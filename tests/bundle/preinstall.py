#!/usr/bin/env python3
"""Verify the scan-handler bundle is complete and executable before installation."""

import importlib.util
from pathlib import Path
import plistlib
import stat
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
  "preinstall_app_verifier", ROOT / "scripts/verify_pdf_opener_bundle.py")
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


class PreinstallBundleTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory(prefix="opener-preinstall-")
    self.addCleanup(self.temp.cleanup)
    self.root = Path(self.temp.name)
    self.app = self.root / "PDF Magic Opener.app"
    self.files = {
      "Contents/Info.plist": plistlib.dumps(verifier.METADATA),
      "Contents/MacOS/PDFOpener": b"native scan helper",
      "Contents/MacOS/MakePDFMagicDefault": b"explicit default-setting helper",
      "Contents/Resources/twilight-reading.png": b"\x89PNG\r\n\x1a\nimage fixture",
    }
    for name, data in self.files.items():
      target = self.app / name
      target.parent.mkdir(parents=True, exist_ok=True)
      target.write_bytes(data)
      target.chmod(0o755 if name in verifier.EXECUTABLES else 0o644)

  def verify(self):
    verifier.verify_bundle(self.app)

  def test_valid_staged_bundle_and_optional_codesign_resources(self):
    self.verify()
    signed = self.app / "Contents/_CodeSignature/CodeResources"
    signed.parent.mkdir()
    signed.write_bytes(b"ad hoc signature fixture")
    self.verify()

  def test_missing_and_nonexecutable_binaries_rejected(self):
    for name in verifier.EXECUTABLES:
      binary = self.app / name
      with self.subTest(name=name, problem="permissions"):
        binary.chmod(0o644)
        with self.assertRaisesRegex(ValueError, "not executable"):
          self.verify()
        binary.chmod(0o755)
      with self.subTest(name=name, problem="missing"):
        data = binary.read_bytes()
        binary.unlink()
        with self.assertRaisesRegex(ValueError, "Missing required"):
          self.verify()
        binary.write_bytes(data)
        binary.chmod(0o755)
      with self.subTest(name=name, problem="empty"):
        binary.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "Empty app file"):
          self.verify()
        binary.write_bytes(data)

  def test_reject_invalid_metadata_and_pdf_claim(self):
    plist = self.app / "Contents/Info.plist"
    for key, value in (
      ("CFBundleIdentifier", "example.untrusted"),
      ("CFBundleExecutable", "MissingExecutable"),
      ("LSMinimumSystemVersion", "10.0"),
      ("CFBundleDocumentTypes", []),
      ("LSUIElement", False),
    ):
      with self.subTest(key=key):
        info = dict(verifier.METADATA)
        info[key] = value
        plist.write_bytes(plistlib.dumps(info))
        with self.assertRaisesRegex(ValueError, "Unexpected app"):
          self.verify()
    plist.write_bytes(b"not a plist")
    with self.assertRaisesRegex(ValueError, "Malformed"):
      self.verify()

  def test_reject_missing_or_invalid_resources(self):
    image = self.app / "Contents/Resources/twilight-reading.png"
    image.write_bytes(b"not a png")
    with self.assertRaisesRegex(ValueError, "artwork"):
      self.verify()
    image.unlink()
    with self.assertRaisesRegex(ValueError, "Missing required"):
      self.verify()

  def test_reject_symlink_escape_and_unexpected_files(self):
    external = self.root / "external"
    external.write_bytes(b"outside")
    rogue = self.app / "Contents/Resources/other"
    rogue.symlink_to(external)
    with self.assertRaisesRegex(ValueError, "Symlinks"):
      self.verify()
    rogue.unlink()
    rogue.write_bytes(b"unexpected")
    with self.assertRaisesRegex(ValueError, "Unexpected app file"):
      self.verify()
    rogue.unlink()
    target = self.app / "Contents/MacOS/PDFOpener"
    target.unlink()
    target.symlink_to(external)
    with self.assertRaisesRegex(ValueError, "Symlinks"):
      self.verify()

  def test_reject_directory_in_place_of_executable_and_excess_permissions(self):
    binary = self.app / "Contents/MacOS/PDFOpener"
    binary.unlink()
    binary.mkdir()
    with self.assertRaisesRegex(ValueError, "Unexpected app directory"):
      self.verify()
    binary.rmdir()
    binary.write_bytes(b"restored")
    binary.chmod(0o777)
    with self.assertRaisesRegex(ValueError, "Unsafe file permissions"):
      self.verify()

  def test_reject_wrong_bundle_name(self):
    self.app = self.app.rename(self.root / "Impostor.app")
    with self.assertRaisesRegex(ValueError, "Expected a real"):
      self.verify()

  def test_installer_validates_signed_staging_before_replacing_installed_app(self):
    source = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    for needed in (
      "mktemp -d",
      'codesign --force --sign - "$app"',
      'python3 "$script_dir/scripts/verify_pdf_opener_bundle.py" "$app"',
      'mv "$app" "$installed_app"',
      'mv "$installed_app" "$bundle_stage_dir/previous.app"',
      'trap cleanup_bundle_stage EXIT',
    ):
      with self.subTest(needed=needed):
        self.assertIn(needed, source)
    self.assertLess(
      source.index('python3 "$script_dir/scripts/verify_pdf_opener_bundle.py" "$app"'),
      source.index('mv "$app" "$installed_app"'),
    )
    self.assertLess(source.index('codesign --force --sign - "$app"'),
                    source.index('python3 "$script_dir/scripts/verify_pdf_opener_bundle.py" "$app"'))
    self.assertIn('python3 - "$app" "$install_dir" "$app_name" <<\x27CONFIG\x27', source)


if __name__ == "__main__":
  unittest.main()
