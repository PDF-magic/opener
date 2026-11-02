#!/usr/bin/env python3
"""Guard the documented, development-only extension delivery policy (opener-1159)."""

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / "docs" / "extension-update-delivery.md"
WEB = ROOT / "extensions" / "webextension"


class ExtensionUpdateDeliveryTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.doc = DOC_PATH.read_text(encoding="utf-8")
    cls.manifest = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
    cls.package = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    cls.gecko = json.loads((WEB / "firefox" / "gecko.json").read_text(encoding="utf-8"))

  def test_current_distribution_is_never_mistaken_for_a_release(self):
    for phrase in (
      "development-only", "no production browser extension is published",
      "no active extension auto-updater", "Not active", "Scan PDF",
      "NOT RELEASE READY", "manual", "disposable profile",
      "unsigned ZIP", "temporary add-ons",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.doc.lower())
    self.assertNotIn("update_url", self.manifest)
    self.assertNotIn("update_url", self.gecko.get("gecko", {}))
    self.assertIn("example.invalid", self.gecko["gecko"]["id"])

  def test_each_publisher_and_browser_family_has_a_separate_update_route(self):
    for name in (
      "Chrome Web Store", "Brave", "Arc", "Vivaldi",
      "Microsoft Edge Add-ons", "Opera Add-ons", "Firefox AMO (listed)",
      "Firefox AMO (unlisted)", "Safari Mac App Store", "Safari Developer ID",
    ):
      with self.subTest(channel=name):
        self.assertIn(name, self.doc)
    for action in ("npm run build", "npm run package:firefox",
                   "about:debugging#/runtime/this-firefox",
                   "PDFMagicOpenerSafari.appex", "Safari Settings"):
      self.assertIn(action, self.doc)

  def test_versions_and_security_gates_are_preserved(self):
    self.assertEqual(self.manifest["version"], self.package["version"])
    self.assertEqual(self.manifest["permissions"], [])
    self.assertEqual(self.manifest["host_permissions"], [])
    self.assertEqual(self.manifest["optional_permissions"], ["downloads"])
    self.assertEqual(self.manifest["incognito"], "not_allowed")
    for phrase in (
      "release version scheme", "stable store extension/Gecko ID",
      "publisher-confirmed identities", "native allowlists",
      "browser storage", "optional permission", "private-browsing",
      "selected PDF destination", "signature freshness",
      "file-integrity", "quarantine", "scan-before-open",
      "no new origins", "not a delivery mechanism", "rolled-back",
    ):
      with self.subTest(gate=phrase):
        self.assertIn(phrase.lower(), self.doc.lower())

  def test_every_local_markdown_link_is_real(self):
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", self.doc):
      if "://" in target:
        continue
      path = target.split("#", 1)[0]
      if path:
        with self.subTest(path=path):
          self.assertTrue((DOC_PATH.parent / path).is_file(), path)
    self.assertIn(
      "[Browser extension update delivery](extension-update-delivery.md)",
      (ROOT / "docs" / "README.md").read_text(encoding="utf-8"),
    )

  def test_required_ci_executes_policy_contract(self):
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    section = workflow.split("\n  scanner-tests:\n", 1)[1]
    section = re.split(r"(?m)^  [a-z][a-z0-9-]*:\s*$", section, maxsplit=1)[0]
    self.assertIn(
      "PYTHONPATH=. python3 tests/general/extension-update-delivery.py -v",
      section,
    )


if __name__ == "__main__":
  unittest.main()
