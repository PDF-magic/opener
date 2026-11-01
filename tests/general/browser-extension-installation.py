#!/usr/bin/env python3
"""Validate truthful development extension installation instructions (opener-1121)."""

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "browser-extension-installation.md"
WEB = ROOT / "extensions" / "webextension"


class BrowserExtensionInstallationDocumentationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.doc = DOC.read_text(encoding="utf-8")
    cls.package = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    cls.manifest = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
    cls.gecko = json.loads((WEB / "firefox" / "gecko.json").read_text(encoding="utf-8"))

  def test_index_links_to_installation_guide(self):
    self.assertIn(
      "[Browser extension installation](browser-extension-installation.md)",
      (ROOT / "docs" / "README.md").read_text(encoding="utf-8"),
    )
    self.assertTrue(DOC.is_file())
    for target in (
      ROOT / "README.md",
      WEB / "README.md",
      ROOT / "extensions" / "safari" / "README.md",
      ROOT / "docs" / "browser-extension-distribution.md",
    ):
      with self.subTest(target=target):
        self.assertTrue(target.is_file())

  def test_build_commands_are_real_and_outputs_are_separate(self):
    for script in ("build", "package:chrome", "package:firefox", "validate:manifests", "test"):
      with self.subTest(script=script):
        self.assertIn(script, self.package["scripts"])
        self.assertIn(f"npm run {script}" if script != "test" else "npm test", self.doc)
    for path in (
      "extensions/webextension/dist/",
      "extensions/webextension/dist/firefox/",
      "dist/chrome/pdf-magic-opener-chrome-<version>.zip",
      "dist/firefox-packages/pdf-magic-opener-firefox-<version>-unsigned.zip",
    ):
      self.assertIn(path, self.doc)
    self.assertIn("Node.js 20", self.doc)
    self.assertIn("Load unpacked", self.doc)
    self.assertIn("Load Temporary Add-on", self.doc)

  def test_browser_instructions_name_each_management_page(self):
    for scheme in (
      "chrome://extensions", "brave://extensions", "edge://extensions",
      "vivaldi://extensions", "opera:extensions", "arc://extensions",
      "about:debugging#/runtime/this-firefox",
    ):
      with self.subTest(scheme=scheme):
        self.assertIn(scheme, self.doc)
    for name in ("Chromium", "Google Chrome", "Brave", "Microsoft Edge", "Vivaldi", "Opera", "Arc", "Firefox"):
      with self.subTest(browser=name):
        self.assertIn(name, self.doc)

  def test_inactive_permissions_and_signing_boundaries(self):
    self.assertEqual(self.manifest["permissions"], [])
    self.assertEqual(self.manifest["host_permissions"], [])
    self.assertEqual(self.manifest["optional_permissions"], ["downloads"])
    self.assertEqual(self.manifest["incognito"], "not_allowed")
    self.assertIn("example.invalid", self.gecko["gecko"]["id"])
    for warning in (
      "inactive development scaffolds", "Not active", "Scan PDF", "disabled",
      "does not scan, sanitize, intercept, or open PDFs",
      "do not", "ClamAV", "quarantine", "file", "unsigned",
      "not a signed XPI", "Mozilla signing", "disposable browser profile",
    ):
      with self.subTest(warning=warning):
        self.assertIn(warning.lower(), self.doc.lower())
    self.assertNotIn("disable signature enforcement", self.doc.lower())

  def test_safari_and_release_channels_are_not_confused_with_development(self):
    for token in (
      "Safari → Settings → Extensions", "PDFMagicOpenerSafari.appex",
      "signed", "notarized", "Chrome Web Store", "Edge Add-ons",
      "Opera Add-ons", "Firefox AMO", "Safari", "Remove",
      "browser-extension-distribution.md",
    ):
      with self.subTest(token=token):
        self.assertIn(token, self.doc)
    self.assertIn("no published", self.doc.lower())
    self.assertIn("not a signed/notarized public installer", self.doc.lower())

  def test_required_scanner_ci_runs_installation_docs_test(self):
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    self.assertIn("scanner-tests:", workflow)
    section = workflow.split("  scanner-tests:", 1)[1].split("\n  ", 1)[0]
    self.assertIn(
      "PYTHONPATH=. python3 tests/general/browser-extension-installation.py -v",
      section,
    )


if __name__ == "__main__":
  unittest.main()
