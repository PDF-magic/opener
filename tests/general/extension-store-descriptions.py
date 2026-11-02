#!/usr/bin/env python3
"""Keep proposed browser-store copy truthful to inactive extensions (opener-1151)."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "extension-store-descriptions.md"
WEB = ROOT / "extensions" / "webextension"
EXPECTED = (
  "Chrome Web Store",
  "Microsoft Edge Add-ons",
  "Opera Add-ons",
  "Firefox AMO",
  "Safari App Store",
)


def parse_store_copy():
  contents = DOC.read_text(encoding="utf-8")
  sections = re.split(r"(?m)^## (.+)\n", contents)
  parsed = {}
  for title, body in zip(sections[1::2], sections[2::2]):
    fields = re.findall(
      r"(?ms)^### (Short description|Full description)\n\n~~~text\n(.*?)\n~~~$",
      body,
    )
    if len(fields) != 2:
      raise AssertionError(f"{title}: expected exactly two copy-ready fields")
    parsed[title] = dict(fields)
  return contents, parsed


class ExtensionStoreDescriptionsTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.document, cls.stores = parse_store_copy()
    cls.chrome = json.loads((WEB / "manifest.json").read_text(encoding="utf-8"))
    cls.firefox = json.loads((WEB / "firefox" / "gecko.json").read_text(encoding="utf-8"))
    cls.safari = json.loads(
      (ROOT / "extensions" / "safari" / "manifest.json").read_text(encoding="utf-8")
    )

  def test_exact_intended_stores_have_copy_ready_descriptions(self):
    self.assertEqual(set(self.stores), set(EXPECTED))
    for channel, fields in self.stores.items():
      with self.subTest(channel=channel):
        self.assertEqual(set(fields), {"Short description", "Full description"})
        short = fields["Short description"]
        full = fields["Full description"]
        self.assertEqual(short, short.strip())
        self.assertNotIn("\n", short)
        self.assertTrue(25 <= len(short) <= 132, (channel, len(short)))
        self.assertTrue(250 <= len(full) <= 5000, (channel, len(full)))
        self.assertEqual(full, full.strip())
        self.assertNotIn("~~~", full)

  def test_each_listing_discloses_inactive_scanner_and_permission_boundary(self):
    self.assertEqual(self.chrome["name"], "PDF Magic Opener")
    self.assertEqual(self.chrome["incognito"], "not_allowed")
    self.assertIn("Not active", self.chrome["description"])
    self.assertEqual(self.chrome["permissions"], [])
    self.assertEqual(self.chrome["host_permissions"], [])
    self.assertEqual(self.chrome["optional_permissions"], ["downloads"])
    self.assertEqual(self.safari["permissions"], ["nativeMessaging"])
    self.assertEqual(self.safari["host_permissions"], [])
    self.assertEqual(self.safari["optional_permissions"], ["downloads"])
    self.assertEqual(self.firefox["gecko"]["id"], "pdf-magic-opener@example.invalid")
    for channel, fields in self.stores.items():
      with self.subTest(channel=channel):
        copy = fields["Full description"]
        for required in (
          "Not active",
          "cannot scan, sanitize, or open PDF files",
          "does not intercept",
          "ClamAV",
          "macOS",
          "optional",
          "monitoring is not active",
        ):
          self.assertIn(required, copy)
        for forbidden in (
          "guarantees safety", "automatically scans PDFs", "protects every PDF",
          "available to install now", "scan is complete", "malware-free",
        ):
          self.assertNotIn(forbidden, copy.lower())

  def test_channel_claims_and_release_blockers_are_distinct(self):
    for channel, browser in (
      ("Chrome Web Store", "Chrome"),
      ("Microsoft Edge Add-ons", "Edge"),
      ("Opera Add-ons", "Opera"),
      ("Firefox AMO", "Firefox"),
      ("Safari App Store", "Safari"),
    ):
      self.assertIn(browser, self.stores[channel]["Full description"])
    self.assertIn("nativeMessaging", self.stores["Safari App Store"]["Full description"])
    self.assertIn("no verified scan-before-render", self.stores["Safari App Store"]["Full description"])
    for channel in EXPECTED[:-1]:
      self.assertIn("no required", self.stores[channel]["Full description"].lower())
    for required in (
      "NOT RELEASE READY", "not submitted", "not approved", "not published",
      "opener-1152", "Gecko", "Mozilla signing", "publisher review",
      "Brave", "Arc", "Vivaldi",
    ):
      self.assertIn(required, self.document)
    self.assertNotIn("@example.invalid", "\n".join(
      fields["Full description"] for fields in self.stores.values()
    ))

  def test_required_distribution_ci_runs_regression(self):
    workflow = (ROOT / ".github" / "workflows" / "distribution-readiness.yml").read_text(
      encoding="utf-8"
    )
    for trigger in ("pull_request:", "merge_group:", "push:"):
      self.assertIn(trigger, workflow)
    self.assertIn(
      "PYTHONPATH=. python3 tests/general/extension-store-descriptions.py -v",
      workflow,
    )
    self.assertLess(
      workflow.index("python3 tests/general/extension-distribution.py -v"),
      workflow.index("python3 tests/general/extension-store-descriptions.py -v"),
    )


if __name__ == "__main__":
  unittest.main()
