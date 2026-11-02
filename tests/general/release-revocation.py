#!/usr/bin/env python3
"""Read-only regression contracts for compromised release revocation."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/release-revocation.md"


class ReleaseRevocationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.content = POLICY.read_text(encoding="utf-8")
    cls.lower = cls.content.lower()

  def test_policy_does_not_claim_live_signed_distribution(self):
    for term in ("not release ready", "source-only",
                 "not authorization", "no public installable",
                 "no signing infrastructure"):
      with self.subTest(term=term):
        self.assertIn(term, self.lower)

  def test_private_incident_containment_and_evidence(self):
    for term in ("incident lead", "private", "utc", "sha-256",
                 "published bytes", "preserve immutable evidence",
                 "stop all new publication", "cancel queued publishing jobs",
                 "rotate/revoke", "direct github ui/api publication"):
      with self.subTest(term=term):
        self.assertIn(term, self.lower)

  def test_withdrawal_handles_all_real_and_conditional_surfaces(self):
    for term in ("gh release edit vx.y.z --draft",
                 "gh release delete-asset vx.y.z asset --yes",
                 "unauthenticated client", "github actions artifacts",
                 "git tag and source checkout", "browser extensions",
                 "macos signed or notarized build",
                 "source-only / manual installation",
                 "never move or reuse a published tag", "never force-push",
                 "does not necessarily uninstall",
                 "cannot be remotely revoked"):
      with self.subTest(term=term):
        self.assertIn(term, self.lower)

  def test_warning_and_verified_recovery(self):
    for term in ("withdrawn / do not install", "non-exploit warning",
                 "new version from a clean commit and new tag",
                 "critical ci", "sha-256 checks", "scanner fail-closed",
                 "quarantine", "integrity", "native messaging allowlists",
                 "saved browser", "preferences", "separately approved",
                 "remaining caches", "post-incident review"):
      with self.subTest(term=term):
        self.assertIn(term, self.lower)

  def test_policy_links_and_discovery(self):
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    self.assertIn("[Compromised release revocation](release-revocation.md)", index)
    self.assertIn("docs/release-revocation.md", security)
    for target in re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", self.content):
      with self.subTest(target=target):
        self.assertTrue((POLICY.parent / target).is_file(), target)

  def test_release_gate_ci_executes_contract(self):
    workflow = (ROOT / ".github/workflows/release-gate-tests.yml").read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/general/release-revocation.py -v", workflow)
    publisher = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    self.assertIn("workflow_dispatch:", publisher)
    self.assertIn("gh release create", publisher)
    self.assertIn("--draft", publisher)


if __name__ == "__main__":
  unittest.main()
