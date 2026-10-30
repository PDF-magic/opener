#!/usr/bin/env python3
"""Audit unsigned browser packages and release-signing prerequisites (opener-0613)."""
import json
from pathlib import Path
import plistlib
import unittest
from zipfile import ZIP_STORED, ZipFile

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "extensions" / "webextension"
DIST = WEB / "dist"
DOC = ROOT / "docs" / "browser-extension-distribution.md"
FILES = (
  "manifest.json", "background.js", "popup.html", "popup.css",
  "icons/icon-16.png", "icons/icon-32.png", "icons/icon-48.png", "icons/icon-128.png",
)
CHANNELS = (
  "Chrome Web Store", "Microsoft Edge Add-ons", "Opera Add-ons",
  "Firefox AMO (listed)", "Firefox AMO (unlisted)",
  "Safari Mac App Store", "Safari Developer ID", "Unpacked development",
  "Brave", "Arc", "Vivaldi", "Chromium",
)


def read_json(path):
  return json.loads(path.read_text(encoding="utf-8"))


class DistributionReadinessTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.manifest = read_json(WEB / "manifest.json")
    cls.gecko = read_json(WEB / "firefox" / "gecko.json")

  def check_unsigned_package(self, folder, filename, manifest):
    archive = DIST / folder / filename
    self.assertTrue(archive.is_file(), f"Missing unsigned archive: {archive}")
    self.assertFalse(archive.is_symlink())
    with ZipFile(archive) as zip_file:
      self.assertEqual(zip_file.namelist(), list(FILES))
      self.assertIsNone(zip_file.testzip())
      self.assertEqual(zip_file.comment, b"")
      for name in FILES:
        entry = zip_file.getinfo(name)
        with self.subTest(archive=filename, entry=name):
          self.assertEqual(entry.compress_type, ZIP_STORED)
          self.assertEqual(zip_file.read(name), (DIST / ("firefox" if folder == "firefox-packages" else "") / name).read_bytes())
      self.assertEqual(json.loads(zip_file.read("manifest.json")), manifest)

  def test_chrome_store_and_chromium_family_upload_zip(self):
    manifest = self.manifest
    self.assertEqual(manifest["manifest_version"], 3)
    self.assertEqual(manifest["background"], {"service_worker": "background.js", "type": "module"})
    self.assertEqual(manifest["incognito"], "not_allowed")
    self.assertEqual(manifest["permissions"], [])
    self.assertEqual(manifest["host_permissions"], [])
    self.assertEqual(manifest["optional_permissions"], ["downloads"])
    self.assertEqual(manifest["action"]["default_title"], "PDF Magic Opener (not active)")
    self.assertNotIn("key", manifest)  # No developer private key/extension identity embedded.
    built = read_json(DIST / "manifest.json")
    self.assertEqual(built, manifest)
    self.check_unsigned_package("chrome", f"pdf-magic-opener-chrome-{manifest['version']}.zip", manifest)

  def test_firefox_amo_submission_is_unsigned_and_uses_development_id(self):
    # AMO listed and unlisted both require Mozilla signing, not a locally signed ZIP.
    self.assertEqual(self.gecko["gecko"]["id"], "pdf-magic-opener@example.invalid")
    expected = dict(self.manifest)
    expected["background"] = {"scripts": ["background.js"]}
    expected["browser_specific_settings"] = self.gecko
    self.assertEqual(read_json(DIST / "firefox" / "manifest.json"), expected)
    self.check_unsigned_package(
      "firefox-packages",
      f"pdf-magic-opener-firefox-{self.manifest['version']}-unsigned.zip",
      expected,
    )

  def test_safari_requires_distribution_signing_not_unsigned_ci_build(self):
    project = (ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj").read_text(encoding="utf-8")
    self.assertIn('name = "Embed App Extensions";', project)
    self.assertIn("PDFMagicOpenerSafari.appex", project)
    self.assertIn("PRODUCT_BUNDLE_IDENTIFIER = local.studio.pdfmagicopener.swiftui.safari;", project)
    self.assertGreaterEqual(project.count("CODE_SIGN_STYLE = Automatic;"), 4)
    with (ROOT / "extensions" / "safari" / "Info.plist").open("rb") as file:
      info = plistlib.load(file)
    self.assertEqual(info["NSExtension"]["NSExtensionPointIdentifier"], "com.apple.Safari.web-extension")
    with (ROOT / "extensions" / "safari" / "SafariExtension.entitlements").open("rb") as file:
      self.assertEqual(plistlib.load(file), {"com.apple.security.app-sandbox": True})
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    self.assertIn("CODE_SIGNING_ALLOWED=NO build", ci)
    self.assertIn("python3 test-safari-extension-target.py --verify-built-app", ci)

  def test_each_channel_documents_signing_and_release_blockers(self):
    doc = DOC.read_text(encoding="utf-8")
    for channel in CHANNELS:
      with self.subTest(channel=channel):
        self.assertIn(channel, doc)
    self.assertIn("NOT RELEASE READY", doc)
    for required in (
      "developer.chrome.com/docs/webstore/prepare",
      "learn.microsoft.com/en-us/microsoft-edge/extensions/publish/hosting-and-updating",
      "help.opera.com/en/extensions/publishing-guidelines",
      "extensionworkshop.com/documentation/publish/signing-and-distribution-overview",
      "developer.apple.com/documentation/safariservices/distributing-your-safari-web-extension",
      "Mozilla signing", "Developer ID", "notarization", "example.invalid",
      "not a signed XPI", "not a signed CRX",
    ):
      with self.subTest(required=required):
        self.assertIn(required, doc)

  def test_dedicated_ci_audits_both_packages(self):
    workflow = (ROOT / ".github" / "workflows" / "distribution-readiness.yml").read_text(encoding="utf-8")
    for trigger in ("pull_request:", "merge_group:", "push:"):
      self.assertIn(trigger, workflow)
    self.assertLess(workflow.index("npm run package:chrome"), workflow.index("python3 test-extension-distribution.py -v"))
    self.assertLess(workflow.index("npm run package:firefox"), workflow.index("python3 test-extension-distribution.py -v"))
    self.assertIn("python3 test-safari-extension-target.py -v", workflow)
    self.assertNotIn("CODE_SIGNING_ALLOWED=YES", workflow)



if __name__ == "__main__":
  unittest.main()
