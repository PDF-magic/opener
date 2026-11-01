#!/usr/bin/env python3
"""Guard user-facing limitations against the disabled interception implementation."""

import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/automatic-interception-limitations.md"
ROUTES = ROOT / "docs/browser-unsupported-routes.md"
INDEX = ROOT / "docs/README.md"
MATRIX = ROOT / "docs/browser-automatic-interception-capabilities.json"
POLICY = ROOT / "extensions/webextension/src/automatic-interception-capability-matrix.js"
BACKGROUND = ROOT / "extensions/webextension/src/background.js"
CI = ROOT / ".github/workflows/ci.yml"


class AutomaticInterceptionLimitationsDocsTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = GUIDE.read_text(encoding="utf-8")
    cls.policy = POLICY.read_text(encoding="utf-8")
    cls.matrix = json.loads(MATRIX.read_text(encoding="utf-8"))

  def test_all_supported_browsers_and_inactive_status(self):
    browser_ids = set(re.findall(
      r'^\s*\["([a-z]+)", "[^"]+", "(?:chromium|gecko|webkit)"',
      self.policy, flags=re.MULTILINE
    ))
    self.assertEqual(len(browser_ids), 9)
    for browser_id in browser_ids:
      with self.subTest(browser=browser_id):
        self.assertIn(f"`{browser_id}`", self.guide)
    self.assertFalse(self.matrix["interceptionEnabled"])
    self.assertFalse(self.matrix["allPathPreOpenVetoProven"])
    self.assertEqual(len(self.matrix["browsers"]), len(browser_ids))
    self.assertTrue(all(
      not row["allPathPreOpenVetoProven"] for row in self.matrix["browsers"]
    ))
    self.assertIn('deployment: "inactive"', self.policy)
    self.assertIn('nativeScanInterlockVerified: false', self.policy)
    self.assertIn("void 0;", BACKGROUND.read_text(encoding="utf-8"))

  def test_every_canonical_entry_path_has_an_explained_limit(self):
    match = re.search(
      r"export const AUTOMATIC_INTERCEPTION_PDF_PATHS = Object\.freeze\(\[([\s\S]*?)\]\);",
      self.policy
    )
    self.assertIsNotNone(match)
    identifiers = re.findall(r'"([^"]+)"', match.group(1))
    self.assertEqual(len(identifiers), 10)
    for identifier in identifiers:
      with self.subTest(path=identifier):
        self.assertRegex(
          self.guide,
          r"(?m)^\| `" + re.escape(identifier) + r"` \| \S.+ \|$"
        )

  def test_enforcement_limits_and_manual_safety_floor(self):
    for phrase in (
      "automatic PDF interception is inactive in all nine",
      "Monitoring is not enforcement", "policy-installed",
      "filterResponseData", "Safari", "DNR", "host/API grants",
      "denied or revoked", "suspended or restarted",
      "complete bounded PDF bytes", "ClamAV", "fresh signatures",
      "file identity/integrity", "quarantine", "Open With",
      "chosen destination", "unscanned opening", "does **not** enable",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.guide)
    self.assertNotIn("Automatic interception is enabled", self.guide)

  def test_discoverability_links_and_ci(self):
    self.assertIn(
      "(automatic-interception-limitations.md)",
      ROUTES.read_text(encoding="utf-8")
    )
    self.assertIn("(browser-unsupported-routes.md)", INDEX.read_text(encoding="utf-8"))
    ci = CI.read_text(encoding="utf-8")
    self.assertEqual(ci.count(
      "tests/browser/automatic-interception-limitations-docs.py -v"
    ), 1)
    for link in re.findall(r"\]\(([^)]+)\)", self.guide):
      path = link.split("#", 1)[0]
      if "://" not in path:
        with self.subTest(link=link):
          self.assertTrue((GUIDE.parent / path).is_file(), link)


if __name__ == "__main__":
  unittest.main()
