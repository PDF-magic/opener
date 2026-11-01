"""Protect the repository's confidential vulnerability reporting instructions."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "SECURITY.md"
INDEX = ROOT / "docs/README.md"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


class SecurityReportingDocumentationTests(unittest.TestCase):
  def setUp(self):
    self.policy = POLICY.read_text(encoding="utf-8")
    self.normalized = self.policy.lower()

  def test_github_recognized_policy_and_conditional_private_channel(self):
    self.assertTrue(self.policy.startswith("# Security Policy\n"))
    self.assertIn("https://github.com/PDF-magic/opener/security/advisories/new", self.policy)
    self.assertIn("report a vulnerability", self.normalized)
    self.assertIn("not guaranteed", self.normalized)
    self.assertIn("private reporting is unavailable", self.normalized)

  def test_no_sensitive_details_go_into_public_issues(self):
    for phrase in (
        "do not publish exploit details",
        "only to request",
        "a private reporting channel",
        "do not include vulnerability details",
        "tokens, credentials",
        "do not send anyone's private pdf",
        "do not upload malware samples",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.normalized)

  def test_actionable_report_and_disclosure_handling(self):
    for phrase in (
        "security impact", "affected component", "steps to reproduce",
        "expected versus observed", "mitigation", "follow-up questions",
        "no acknowledgement or remediation deadline",
        "coordinate any publication", "ordinary bugs",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.normalized)

  def test_existing_safety_boundaries_are_explicit(self):
    for phrase in (
        "clamav scan gate", "file-integrity checks", "quarantine",
        "selected pdf", "clean scan is not a guarantee",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.normalized)

  def test_policy_is_discoverable_and_checked_by_ci(self):
    self.assertIn("[Security reporting process](../SECURITY.md)",
                  INDEX.read_text(encoding="utf-8"))
    self.assertIn("PYTHONPATH=. python3 tests/general/security-reporting-documentation.py -v",
                  WORKFLOW.read_text(encoding="utf-8"))


if __name__ == "__main__":
  unittest.main()
