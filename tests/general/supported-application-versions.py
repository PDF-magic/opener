#!/usr/bin/env python3
"""Keep the published app-version support policy consistent with release state."""

from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
SECURITY = ROOT / "SECURITY.md"
DOC_INDEX = ROOT / "docs/README.md"
RELEASE_NOTES = ROOT / "docs/release-notes.md"
RELEASE_VERSIONING = ROOT / "docs/release-versioning.md"
CI = ROOT / ".github/workflows/ci.yml"


class SupportedApplicationVersionsTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.policy = SECURITY.read_text(encoding="utf-8")
    cls.notes = RELEASE_NOTES.read_text(encoding="utf-8")

  def test_declared_development_version_matches_all_products(self):
    project = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text(encoding="utf-8")
    mac_versions = set(re.findall(r"MARKETING_VERSION = ([^;]+);", project))
    browser_version = json.loads(
      (ROOT / "extensions/webextension/manifest.json").read_text(encoding="utf-8")
    )["version"]
    package_version = json.loads(
      (ROOT / "extensions/webextension/package.json").read_text(encoding="utf-8")
    )["version"]
    self.assertEqual(mac_versions, {browser_version})
    self.assertEqual(browser_version, package_version)
    self.assertEqual(browser_version, "0.1.0")
    self.assertIn(f"`{browser_version}`", self.policy)
    self.assertIn(f"Development snapshot — {browser_version} (unreleased)", self.notes)

  def test_current_release_state_and_older_versions_are_unambiguous(self):
    self.assertIn("## Supported Versions", self.policy)
    normalized = " ".join(self.policy.split())
    for statement in (
      "No public installable application release has",
      "unreleased development",
      "Older commits and locally built development snapshots",
      "**Unsupported**",
      "**None published; none currently supported.**",
      "**not a supported production build**",
      "**only the newest published stable application version**",
      "ends support for all older stable application versions immediately",
      "no overlapping,",
      "backport window",
      "source-only GitHub Release",
      "Private vulnerability reports are welcome for any version",
    ):
      with self.subTest(statement=statement):
        self.assertIn(statement, normalized)
    self.assertIn("**Publication state: UNRELEASED.**", self.notes)
    self.assertIn("**NOT RELEASE READY**", self.notes)
    self.assertIn("The current checked-in product version is `0.1.0`",
                  RELEASE_VERSIONING.read_text(encoding="utf-8"))

  def test_upgrade_is_not_a_scanner_bypass_or_preference_reset(self):
    for phrase in (
      "trusted-source upgrade and rollback guide",
      "ClamAV scan-before-open", "signature freshness",
      "file-integrity checks", "macOS quarantine",
      "user-selected PDF opener", "Preserve custom",
      "PDF associations", "avoid using the old build",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.policy)
    for link in (
      "docs/release-notes.md", "docs/release-versioning.md",
      "docs/upgrade-process.md",
    ):
      self.assertTrue((ROOT / link).is_file(), link)

  def test_support_policy_is_discoverable_and_ci_enforced(self):
    self.assertIn("[Supported application versions](../SECURITY.md#supported-versions)",
                  DOC_INDEX.read_text(encoding="utf-8"))
    ci_text = CI.read_text(encoding="utf-8")
    self.assertIn("  scanner-tests:", ci_text)
    self.assertIn("tests/general/supported-application-versions.py -v", ci_text)


if __name__ == "__main__":
  unittest.main()
