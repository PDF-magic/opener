#!/usr/bin/env python3
"""Keep the security fix prioritization contract reviewable (opener-1169)."""

from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/security-fix-prioritization.md"


class SecurityFixPrioritizationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = POLICY.read_text(encoding="utf-8")
    cls.lower = cls.guide.lower()

  def test_four_ordered_levels_and_concrete_decisions(self):
    rows = re.findall(r"^\\| \\*\\*(P[0-3]) — [^|]+\\*\\* \\| ([^|]+) \\| ([^|]+) \\|$",
                      self.guide, re.MULTILINE)
    self.assertEqual([row[0] for row in rows], ["P0", "P1", "P2", "P3"])
    for index, phrase in enumerate(("active exploitation", "high-impact",
                                    "constrained reachability", "defense-in-depth")):
      with self.subTest(priority=f"P{index}"):
        self.assertIn(phrase, rows[index][1].lower())
    self.assertIn("interrupt feature", rows[0][2].lower())
    self.assertIn("hold any affected release", rows[1][2].lower())
    self.assertIn("next planned maintenance cycle", rows[2][2].lower())
    self.assertIn("later reviewed maintenance", rows[3][2].lower())

  def test_exposure_driven_triage_and_reassessment(self):
    for phrase in (
      "confidentiality", "integrity", "availability", "reachable attack",
      "evidence of exploitation", "cvss", "not as automatic priority",
      "higher plausible priority provisionally", "weekly dependency audit",
      "monthly review", "reassess immediately", "revise downward only",
      "relative work-order rules", "not guaranteed",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.lower)

  def test_private_evidence_and_fail_closed_remediation(self):
    for phrase in (
      "private", "do not create public issues", "credentials",
      "confidential triage record", "non-destructive",
      "disable or restrict", "only that path", "unscanned opening",
      "stale signatures", "quarantine", "file-integrity checks",
      "fail closed", "regression test", "applicable ci",
      "release gate", "user-selected pdf browser", "custom signatures",
      "finder customizations", "coordinate any advisory",
      "keep the affected opening or distribution path blocked",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.lower)

  def test_discoverability_local_links_and_ci_coverage(self):
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("[Security fix prioritization](security-fix-prioritization.md)", index)
    self.assertIn("[security fix prioritization](docs/security-fix-prioritization.md)", security)
    self.assertIn("PYTHONPATH=. python3 tests/general/security-fix-prioritization.py -v", ci)
    for target in re.findall(r"(?<!!)\\[[^\\]]+\\]\\(([^)]+)\\)", self.guide):
      url = urlsplit(target)
      if not url.scheme and not url.netloc and url.path:
        with self.subTest(target=target):
          self.assertTrue((POLICY.parent / url.path).is_file(), target)


if __name__ == "__main__":
  unittest.main()
