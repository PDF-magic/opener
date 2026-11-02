#!/usr/bin/env python3
"""Guard browser store privacy disclosures against real packaged manifests (opener-1152)."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "extensions" / "webextension"
DOC = ROOT / "docs" / "browser-extension-privacy-disclosures.md"


def load_manifest(path):
  return json.loads(path.read_text(encoding="utf-8"))


class ExtensionPrivacyDisclosureTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.source = load_manifest(WEB / "manifest.json")
    cls.chromium = load_manifest(WEB / "dist" / "manifest.json")
    cls.firefox = load_manifest(WEB / "dist" / "firefox" / "manifest.json")
    cls.safari = load_manifest(ROOT / "extensions" / "safari" / "manifest.json")
    cls.policy = DOC.read_text(encoding="utf-8")

  def test_declared_permissions_match_privacy_claims(self):
    for label, manifest, required in (
      ("source", self.source, []),
      ("Chromium package", self.chromium, []),
      ("Firefox package", self.firefox, []),
      ("Safari", self.safari, ["nativeMessaging"]),
    ):
      with self.subTest(browser=label):
        self.assertEqual(manifest["permissions"], required)
        self.assertEqual(manifest["host_permissions"], [])
        self.assertEqual(manifest["optional_permissions"], ["downloads"])
        self.assertNotIn("optional_host_permissions", manifest)
        self.assertNotIn("content_scripts", manifest)
        self.assertEqual(manifest["incognito"], "not_allowed")
        self.assertIn("not active", manifest["action"]["default_title"].lower())
    self.assertEqual(self.chromium, self.source)
    self.assertEqual(
      self.firefox["browser_specific_settings"]["gecko"]["data_collection_permissions"],
      {"required": ["none"]},
    )
    self.assertEqual(
      self.firefox["background"], {"scripts": ["background.js"]},
    )

  def test_inactive_background_and_safari_handler_support_no_collection_claim(self):
    background = (WEB / "src" / "background.js").read_text(encoding="utf-8")
    self.assertEqual(
      background,
      "// Inactive shared WebExtensions background entry point.\n"
      "// Do not listen for messages, inspect PDFs or request native access here.\n"
      "void 0;\n",
    )
    handler = (
      ROOT / "extensions" / "safari" / "SafariWebExtensionHandler.swift"
    ).read_text(encoding="utf-8")
    self.assertIn('topic == "native.status"', handler)
    self.assertIn('"status": "inactive"', handler)
    self.assertIn('"scanVerified": false', handler)
    self.assertIn('"authorizesOpen": false', handler)

  def test_policy_covers_actual_data_and_permission_boundaries(self):
    plain_policy = " ".join(self.policy.replace("**", "").split())
    for statement in (
      "DRAFT — NOT PUBLISHED OR RELEASE READY",
      "No user data is collected or transmitted by the current browser extension.",
      "PDF files or their contents",
      "download source URLs",
      "browsing histories",
      "cookies",
      "credentials",
      "analytics",
      "does not sell user data",
      "no extension-collected records",
      "optional `downloads`",
      '["none"]',
      "nativeMessaging",
      "native.status",
      "separately installed macOS application",
      "signature freshness",
      "quarantine",
      "publisher-controlled privacy",
      "affirmative consent",
    ):
      with self.subTest(statement=statement):
        self.assertIn(statement, plain_policy)

  def test_store_copy_and_release_blockers_are_explicit(self):
    for store in (
      "Chrome Web Store", "Microsoft Edge Add-ons", "Opera Add-ons",
      "Firefox AMO", "Safari",
    ):
      with self.subTest(store=store):
        self.assertIn("| **" + store + "**", self.policy)
    for field in (
      "Privacy practices", "Partner Center", "privacy policy URL",
      "privacy contact", "actual channel artifact", "NOT PUBLISHED",
      "not a", "before enabling downloads monitoring",
    ):
      with self.subTest(field=field):
        self.assertIn(field.lower(), self.policy.lower())
    overview = (ROOT / "docs" / "browser-extension-distribution.md").read_text(encoding="utf-8")
    self.assertIn("browser-extension-privacy-disclosures.md", overview)

  def test_required_distribution_ci_enforces_disclosure_audit(self):
    workflow = (
      ROOT / ".github" / "workflows" / "distribution-readiness.yml"
    ).read_text(encoding="utf-8")
    command = "python3 tests/general/extension-privacy-disclosures.py -v"
    self.assertIn("pull_request:", workflow)
    self.assertIn("merge_group:", workflow)
    self.assertIn(command, workflow)
    self.assertLess(workflow.index("npm run package:firefox"), workflow.index(command))
    self.assertLess(workflow.index("npm run package:chrome"), workflow.index(command))


if __name__ == "__main__":
  unittest.main()
