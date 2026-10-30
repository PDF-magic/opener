#!/usr/bin/env python3
"""Portable regression tests for unsigned Safari host-app packaging."""
import importlib.util
import json
from pathlib import Path
import plistlib
import stat
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
  "safari_package", ROOT / "scripts" / "package_safari_extension.py")
safari = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safari)


class SafariPackageTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.app = self.root / "PDFMagicOpener.app"
    host = {"CFBundleIdentifier": "local.studio.pdfmagicopener.swiftui",
            "CFBundlePackageType": "APPL"}
    extension = {
      "CFBundleIdentifier": "local.studio.pdfmagicopener.swiftui.safari",
      "CFBundlePackageType": "XPC!",
      "NSExtension": {
        "NSExtensionPointIdentifier": "com.apple.Safari.web-extension"}}
    self.files = {
      "Contents/Info.plist": plistlib.dumps(host),
      "Contents/MacOS/PDFMagicOpener": b"host fixture executable",
      safari.APPEX + "Info.plist": plistlib.dumps(extension),
      safari.APPEX + "MacOS/PDFMagicOpenerSafari": b"extension fixture executable",
    }
    for name in safari.RESOURCES:
      src = safari.SOURCE / (
        name if name == "manifest.json" or name.startswith("icons/")
        else "src/" + name)
      self.files[safari.APPEX + "Resources/" + name] = src.read_bytes()
    for name, data in self.files.items():
      target = self.app / name
      target.parent.mkdir(parents=True, exist_ok=True)
      target.write_bytes(data)
      if name in safari.EXECUTABLES:
        target.chmod(0o755)

  def test_build_real_zip_and_reproduce_exact_bytes(self):
    archive = safari.package(self.app, self.root / "output")
    self.assertEqual(archive.name, "pdf-magic-opener-safari-0.1.0-unsigned.zip")
    self.assertEqual(safari.verify_archive(archive), "0.1.0")
    self.assertEqual(archive.read_bytes(),
                     safari.package(self.app, self.root / "output").read_bytes())
    with zipfile.ZipFile(archive) as bundle:
      self.assertEqual(bundle.namelist(), sorted(safari.HOST + p for p in self.files))

  def test_reject_unapproved_resource_and_symlink(self):
    unexpected = self.app / "Contents" / "Resources" / "private.key"
    unexpected.parent.mkdir(parents=True, exist_ok=True)
    unexpected.write_bytes(b"not a package resource")
    with self.assertRaises(ValueError):
      safari.package(self.app, self.root / "output")
    unexpected.unlink()
    unexpected.symlink_to(self.app / "Contents" / "Info.plist")
    with self.assertRaises(ValueError):
      safari.package(self.app, self.root / "output")

  def test_reject_missing_binary_and_extended_permissions(self):
    executable = self.app / safari.APPEX / "MacOS" / "PDFMagicOpenerSafari"
    executable.unlink()
    with self.assertRaises(ValueError):
      safari.package(self.app, self.root / "output")
    executable.write_bytes(b"restored")
    executable.chmod(0o755)
    manifest = self.app / safari.APPEX / "Resources" / "manifest.json"
    unsafe = json.loads(manifest.read_text())
    unsafe["permissions"] = ["nativeMessaging"]
    manifest.write_text(json.dumps(unsafe))
    with self.assertRaises(ValueError):
      safari.package(self.app, self.root / "output")

  def test_reject_modified_popup_or_nonexecutable_bundle(self):
    popup = self.app / safari.APPEX / "Resources" / "popup.html"
    popup.write_bytes(b"<script>bad</script>")
    with self.assertRaises(ValueError):
      safari.package(self.app, self.root / "output")
    popup.write_bytes(self.files[safari.APPEX + "Resources/popup.html"])
    executable = self.app / "Contents" / "MacOS" / "PDFMagicOpener"
    executable.chmod(0o644)
    with self.assertRaises(ValueError):
      safari.package(self.app, self.root / "output")

  def test_reject_zip_traversal_missing_assets_and_executable_mode(self):
    archive = safari.package(self.app, self.root / "output")
    with zipfile.ZipFile(archive) as zf:
      originals = [(entry, zf.read(entry)) for entry in zf.infolist()]
    def malformed(transform):
      bad = self.root / "bad.zip"
      with zipfile.ZipFile(bad, "w") as zf:
        for info, payload in originals:
          replacement = transform(info, payload)
          if replacement is not None:
            zf.writestr(*replacement)
      with self.assertRaises(ValueError):
        safari.verify_archive(bad)
    malformed(lambda i, b: None if i.filename.endswith("/manifest.json") else (i, b))
    malformed(lambda i, b: (zipfile.ZipInfo("../escape"), b)
              if i.filename.endswith("/manifest.json") else (i, b))
    def no_execute(info, data):
      if info.filename.endswith("/MacOS/PDFMagicOpenerSafari"):
        info.external_attr = ((stat.S_IFREG | 0o644) << 16)
      return (info, data)
    malformed(no_execute)

  def test_ci_publishes_verified_safari_package(self):
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    self.assertIn("python3 test-safari-extension-package.py -v", ci)
    self.assertIn("scripts/package_safari_extension.py --app", ci)
    self.assertIn("scripts/package_safari_extension.py --verify", ci)
    self.assertIn("pdf-magic-opener-safari-unsigned", ci)
    self.assertIn("actions/upload-artifact@v4", ci)


if __name__ == "__main__":
  unittest.main()
