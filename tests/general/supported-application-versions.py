#!/usr/bin/env python3
"""Guard the source-support policy and required build metadata."""

from pathlib import Path
import json
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
SECURITY = ROOT / "SECURITY.md"
DOC_INDEX = ROOT / "docs/README.md"
BUILD_METADATA = ROOT / "docs/release-versioning.md"
CI = ROOT / ".github/workflows/ci.yml"


class SourceMaintenancePolicyTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.policy = SECURITY.read_text(encoding="utf-8")
    cls.metadata = BUILD_METADATA.read_text(encoding="utf-8")

  def test_required_build_identifiers_remain_valid_and_consistent(self):
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
    self.assertRegex(browser_version, r"^\\d+\\.\\d+\\.\\d+$")
    self.assertIn("Required build metadata", self.metadata)
    self.assertIn("not announcements or promises", self.metadata)

  def test_support_is_commit_based_without_numbered_release_commitments(self):
    for statement in (
      "## Source maintenance and security support",
      "source code on \`main\`",
      "Git commit",
      "Older commits and locally built development",
      "do **not** receive guaranteed maintenance",
      "no newest-stable-version policy",
      "Private vulnerability reports are welcome for any checkout",
      "no formal Semantic",
      "not a release schedule or support promise",
    ):
      with self.subTest(statement=statement):
        self.assertIn(statement.replace("\\`", "`"), self.policy)
    self.assertIn("does **not** use a public Semantic Versioning policy", self.metadata)
    self.assertIn("no need to create `vX.Y.Z` tags", self.metadata)
    self.assertNotIn("only the newest published stable application version", self.policy)

  def test_manual_upgrades_preserve_scanner_and_user_settings(self):
    for marker in (
      "trusted source checkout", "upgrade and rollback guide",
      "Finder actions", "selected PDF associations", "quarantine",
      "signature freshness", "ClamAV", "scan-before-open",
      "file-integrity", "user preferences",
    ):
      with self.subTest(marker=marker):
        self.assertIn(marker.lower(), self.policy.lower())
    for relative in ("docs/release-versioning.md", "docs/upgrade-process.md",
                     "docs/application-update-delivery.md"):
      self.assertTrue((ROOT / relative).is_file(), relative)

  def test_policy_is_discoverable_and_ci_enforced(self):
    idx = DOC_INDEX.read_text(encoding="utf-8")
    self.assertIn(
      "(../SECURITY.md#source-maintenance-and-security-support)", idx)
    self.assertIn("tests/general/supported-application-versions.py -v",
                  CI.read_text(encoding="utf-8"))
    for match in re.findall(r"(?<!!)\\[[^\\]]+\\]\\(([^)]+)\\)", self.policy):
      parsed = urlsplit(match)
      if not parsed.scheme and not parsed.netloc and parsed.path:
        self.assertTrue((ROOT / parsed.path).is_file(), match)


if __name__ == "__main__":
  unittest.main()
