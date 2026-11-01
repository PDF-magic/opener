#!/usr/bin/env python3
"""Verify the packaged macOS app requires native reviewed helper binaries."""
import importlib.util
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "scripts/package_application_helpers.py"
spec = importlib.util.spec_from_file_location("package_application_helpers", PACKAGE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CI = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
INSTALLER = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
PROJECT = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text(encoding="utf-8")


class PackagedHelperTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.app = self.root / "src" / module.APP_NAME
    executable = self.app / "Contents/MacOS/PDFMagicOpener"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"\xcf\xfa\xed\xfe" + b"app")
    executable.chmod(0o755)
    info = dict(CFBundleIdentifier=module.BUNDLE_ID,
                CFBundlePackageType="APPL",
                CFBundleExecutable="PDFMagicOpener", LSUIElement=False)
    with (self.app / "Contents/Info.plist").open("wb") as stream:
      plistlib.dump(info, stream)

  def add_fake_helpers(self, app=None):
    app = app or self.app
    directory = app / module.HELPER_FOLDER
    directory.mkdir(parents=True)
    for name in module.HELPER_NAMES:
      target = directory / name
      target.write_bytes(b"\xcf\xfa\xed\xfe" + b"binary")
      target.chmod(0o755)
    return directory

  def test_helper_list_is_unique_and_follows_installer_sources(self):
    self.assertEqual(len(module.HELPERS), len(module.HELPER_NAMES))
    self.assertIn("pdf-magic-native-host", module.HELPER_NAMES)
    self.assertNotIn("PDFOpener", module.HELPER_NAMES)
    self.assertNotIn("MakePDFMagicDefault", module.HELPER_NAMES)
    self.assertIn("local.studio.brave-pdf-opener", INSTALLER)
    for name, definitions, sources in module.HELPERS:
      self.assertEqual(name, Path(name).name)
      self.assertTrue(sources)
      for source in sources:
        self.assertTrue((ROOT / source).is_file(), source)
      if name != "pdf-magic-native-host":
        self.assertIn('"$install_dir/' + name + '"', INSTALLER)
    self.assertIn('PDFMagicOpenerApp.swift', PROJECT)

  def test_rejects_missing_extra_nonbinary_or_unexecutable_helper(self):
    with self.assertRaises(ValueError):
      module.validate_helpers(self.app)
    helpers = self.add_fake_helpers()
    self.assertEqual(len(module.validate_helpers(self.app)), len(module.HELPER_NAMES))
    chosen = helpers / "launch-scanned-file"
    chosen.chmod(0o644)
    with self.assertRaises(ValueError):
      module.validate_helpers(self.app)
    chosen.chmod(0o755)
    chosen.write_bytes(b"#!/bin/sh\nexit 0\n")
    with self.assertRaises(ValueError):
      module.validate_helpers(self.app)
    chosen.write_bytes(b"\xcf\xfa\xed\xfe" + b"binary")
    (helpers / "unexpected").write_bytes(b"\xcf\xfa\xed\xfe")
    with self.assertRaises(ValueError):
      module.validate_helpers(self.app)
    (helpers / "unexpected").unlink()
    chosen.unlink()
    chosen.symlink_to(helpers / "identify-pdf-handler")
    with self.assertRaises(ValueError):
      module.validate_helpers(self.app)

  def test_never_package_a_pdf_association_or_untrusted_app(self):
    self.add_fake_helpers()
    self.assertEqual(len(module.validate_helpers(self.app)), len(module.HELPER_NAMES))
    info = self.app / "Contents/Info.plist"
    with info.open("rb") as file:
      dictionary = plistlib.load(file)
    dictionary["CFBundleDocumentTypes"] = [{"CFBundleTypeExtensions": ["pdf"]}]
    with info.open("wb") as file:
      plistlib.dump(dictionary, file)
    with self.assertRaises(ValueError):
      module.validate_helpers(self.app)
    dictionary.pop("CFBundleDocumentTypes")
    dictionary["CFBundleIdentifier"] = "local.studio.brave-pdf-opener"
    with info.open("wb") as file:
      plistlib.dump(dictionary, file)
    with self.assertRaises(ValueError):
      module.validate_helpers(self.app)

  def test_staging_never_replaces_existing_app_or_mutates_original(self):
    output = self.root / "dist"
    with patch.object(module.subprocess, "run", side_effect=self.fake_compile) as compiled:
      staged = module.stage(self.app, output, swiftc="/usr/bin/xcrun")
    self.assertEqual(staged, output / module.APP_NAME)
    self.assertEqual(len(module.validate_helpers(staged)), len(module.HELPER_NAMES))
    self.assertFalse((self.app / module.HELPER_FOLDER).exists())
    self.assertEqual(compiled.call_count, len(module.HELPERS))
    with self.assertRaises(ValueError):
      module.stage(self.app, output)
    self.assertTrue(staged.exists())

  def test_rejects_security_fixtures_and_key_material_from_staged_app(self):
    self.add_fake_helpers()
    for path in (
      "Contents/Resources/tests/sample.bin",
      "Contents/Resources/Fixtures/sample.bin",
      "Contents/Resources/pdf-security-corpus/active.bin",
      "Contents/Resources/manual.PDF",
      "Contents/Resources/private.KEY",
      "Contents/Resources/secret.pem",
      "Contents/Resources/signing.p12",
      "Contents/Resources/signing.pfx",
    ):
      with self.subTest(path=path):
        target = self.app / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"synthetic test marker only")
        with self.assertRaisesRegex(ValueError, "Non-distributable"):
          module.validate_helpers(self.app)
        with self.assertRaisesRegex(ValueError, "Non-distributable"):
          module.stage(self.app, self.root / "dist", swiftc="/usr/bin/xcrun")
        shutil.rmtree(self.app / "Contents" / "Resources")
    # The guard must not prohibit ordinary custom app resources.
    resource = self.app / "Contents" / "Resources" / "theme.json"
    resource.parent.mkdir(parents=True, exist_ok=True)
    resource.write_text('{"theme": "original"}', encoding="utf-8")
    self.assertEqual(len(module.validate_helpers(self.app)), len(module.HELPER_NAMES))

  def test_source_release_excludes_security_corpus_without_excluding_normal_files(self):
    paths = (
      "tests/fixtures/pdf-security-corpus/truncated/truncated-eof.pdf",
      "tests/fixtures/pdf-security-corpus/future/embedded-file.pdf",
      "tests/fixtures/empty.pdf",
      "README.md",
    )
    result = subprocess.run(
      ["git", "check-attr", "export-ignore", "--", *paths],
      cwd=ROOT, check=True, capture_output=True, text=True, timeout=15)
    values = dict(line.split(": export-ignore: ", 1)
                  for line in result.stdout.splitlines())
    self.assertEqual(set(values), set(paths))
    for path in paths[:2]:
      self.assertEqual(values[path], "set")
    for path in paths[2:]:
      self.assertEqual(values[path], "unspecified")

  def test_distribution_ci_runs_fixture_isolation_audit(self):
    readiness = (ROOT / ".github/workflows/distribution-readiness.yml").read_text(
      encoding="utf-8")
    self.assertIn("tests/general/application-helper-packaging.py -v", readiness)

  @staticmethod
  def fake_compile(arguments, **kwargs):
    assert arguments[0:2] == ["/usr/bin/xcrun", "swiftc"]
    assert arguments[-2] == "-o"
    if target_name := Path(arguments[-1]).name:
      assert ("-parse-as-library" in arguments) == (target_name != "launch-scanned-file")
    target = Path(arguments[-1])
    target.write_bytes(b"\xcf\xfa\xed\xfe" + b"binary")
    return None

  def test_ci_builds_and_verifies_staged_app_without_mutating_xcode_app(self):
    self.assertIn("tests/general/application-helper-packaging.py -v", CI)
    self.assertIn("scripts/package_application_helpers.py --app", CI)
    self.assertIn("scripts/package_application_helpers.py --verify", CI)
    self.assertIn("scanner-tests:", CI)
    self.assertIn("macos-build:", CI)


if __name__ == "__main__":
  unittest.main()
