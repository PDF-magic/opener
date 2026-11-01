#!/usr/bin/env python3
"""Fail-closed release-gate regressions; no real network or release operations."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/require_release_checks.py"
spec = importlib.util.spec_from_file_location("release_check_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
SHA = "a" * 40
TAG = "v1.2.3"
READY = "**Status: RELEASE READY.**"


def success_runs():
  return [{"name": name, "status": "completed", "conclusion": "success",
           "app": {"slug": "github-actions"}} for name in gate.REQUIRED_CHECKS]


class ReleaseGateTests(unittest.TestCase):
  def test_accepts_only_complete_trusted_critical_checks(self):
    gate.ensure_checks(success_runs())
    for field, value in (("status", "in_progress"), ("conclusion", "failure"),
                         ("conclusion", "skipped"), ("conclusion", "cancelled")):
      runs = success_runs()
      runs[0][field] = value
      with self.subTest(field=field, value=value), self.assertRaises(gate.GateError):
        gate.ensure_checks(runs)

  def test_missing_duplicate_and_untrusted_checks_are_rejected(self):
    runs = success_runs()
    for replacement in (runs[:-1], runs + [runs[0]],
                        [{**runs[0], "app": {"slug": "external"}}] + runs[1:]):
      with self.subTest(replacement=replacement), self.assertRaises(gate.GateError):
        gate.ensure_checks(replacement)

  def test_only_exact_main_ref_and_semver_tag_pass(self):
    gate.ensure_context(gate.REPOSITORY, "refs/heads/main", SHA, TAG, READY)
    for repo, ref, sha, tag in (
      ("other/fork", "refs/heads/main", SHA, TAG),
      (gate.REPOSITORY, "refs/heads/feature", SHA, TAG),
      (gate.REPOSITORY, "refs/tags/" + TAG, SHA, TAG),
      (gate.REPOSITORY, "refs/heads/main", "bad", TAG),
      (gate.REPOSITORY, "refs/heads/main", SHA, "../../bad"),
    ):
      with self.subTest(tag=tag, ref=ref), self.assertRaises(gate.GateError):
        gate.ensure_context(repo, ref, sha, tag, READY)

  def test_release_tag_grammar_is_canonical_stable_semver(self):
    for tag in ("v0.0.0", "v0.1.0", "v1.2.3", "v10.20.30"):
      with self.subTest(tag=tag):
        gate.ensure_context(gate.REPOSITORY, "refs/heads/main", SHA, tag, READY)
    for tag in ("1.2.3", "v1.2", "v1.2.3.4", "v01.2.3", "v1.02.3",
                "v1.2.03", "v1.2.3-rc.1", "v1.2.3+build", "v1.2.3 ",
                "v１.2.3", "v1.2.-3"):
      with self.subTest(tag=tag), self.assertRaises(gate.GateError):
        gate.ensure_context(gate.REPOSITORY, "refs/heads/main", SHA, tag, READY)

  def test_release_versions_match_all_published_component_metadata(self):
    gate.ensure_version_metadata("v0.1.0", ROOT)
    with self.assertRaises(gate.GateError):
      gate.ensure_version_metadata("v0.1.1", ROOT)
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      extension = root / "extensions/webextension"
      project = root / "PDFMagicOpener.xcodeproj"
      extension.mkdir(parents=True)
      project.mkdir()
      (extension / "package.json").write_text('{"version":"0.1.0"}', encoding="utf-8")
      (extension / "manifest.json").write_text('{"version":"0.1.0"}', encoding="utf-8")
      (project / "project.pbxproj").write_text(
        "MARKETING_VERSION = 0.1.0;\nMARKETING_VERSION = 0.1.0;\n", encoding="utf-8")
      gate.ensure_version_metadata("v0.1.0", root)
      for filename in ("package.json", "manifest.json"):
        path = extension / filename
        path.write_text('{"version":"0.1.1"}', encoding="utf-8")
        with self.subTest(filename=filename), self.assertRaises(gate.GateError):
          gate.ensure_version_metadata("v0.1.0", root)
        path.write_text('{"version":"0.1.0"}', encoding="utf-8")
      (project / "project.pbxproj").write_text(
        "MARKETING_VERSION = 0.1.0;\nMARKETING_VERSION = 0.1.1;\n", encoding="utf-8")
      with self.assertRaises(gate.GateError):
        gate.ensure_version_metadata("v0.1.0", root)

  def test_release_versioning_policy_is_discoverable(self):
    guide = (ROOT / "docs/release-versioning.md").read_text(encoding="utf-8")
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    self.assertIn("(release-versioning.md)", index)
    for term in ("MAJOR", "MINOR", "PATCH", "vX.Y.Z", "MARKETING_VERSION",
                 "CURRENT_PROJECT_VERSION", "package.json", "manifest.json",
                 "NOT RELEASE READY", "source-only", "prerelease"):
      with self.subTest(term=term):
        self.assertIn(term, guide)

  def test_distribution_blockers_must_be_explicitly_cleared(self):
    for content in ("**Status: NOT RELEASE READY.**", "", READY + " NOT RELEASE READY"):
      with self.subTest(content=content), self.assertRaises(gate.GateError):
        gate.ensure_context(gate.REPOSITORY, "refs/heads/main", SHA, TAG, content)

  def test_tag_ref_must_resolve_to_verified_commit(self):
    with patch.object(gate, "github_json", side_effect=[{"object": {"type": "tag", "sha": "b"*40}},
                                                      {"object": {"type": "commit", "sha": SHA}}]):
      self.assertEqual(gate.resolve_tag(TAG, "token"), SHA)
    with patch.object(gate, "github_json", return_value={"object": {"type": "tree", "sha": SHA}}):
      with self.assertRaises(gate.GateError):
        gate.resolve_tag(TAG, "token")

  def test_checks_are_paginated_without_silent_truncation(self):
    runs = success_runs()
    with patch.object(gate, "github_json", return_value={"total_count": len(runs), "check_runs": runs}):
      self.assertEqual(gate.get_check_runs(SHA, "token"), runs)
    with patch.object(gate, "github_json", return_value={"total_count": len(runs) + 1, "check_runs": runs}):
      with self.assertRaises(gate.GateError):
        gate.get_check_runs(SHA, "token")

  def test_rejects_moved_main_and_tag_or_failed_checks(self):
    for branch_sha, tag_sha, runs in (("b"*40, SHA, success_runs()),
                                      (SHA, "b"*40, success_runs()),
                                      (SHA, SHA, success_runs()[:-1])):
      with self.subTest(branch_sha=branch_sha, tag_sha=tag_sha):
        with patch.object(gate, "ensure_version_metadata"), \
             patch.object(gate, "github_json", return_value={"commit": {"sha": branch_sha}}), \
             patch.object(gate, "resolve_tag", return_value=tag_sha), \
             patch.object(gate, "get_check_runs", return_value=runs):
          with self.assertRaises(gate.GateError):
            gate.verify_release(gate.REPOSITORY, "refs/heads/main", SHA, TAG, READY, "token")

  def test_release_workflow_cannot_publish_before_gate(self):
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    self.assertIn("workflow_dispatch:", workflow)
    self.assertIn("needs: critical-release-gate", workflow)
    self.assertIn("--verify-tag", workflow)
    self.assertEqual(workflow.count("python3 scripts/require_release_checks.py --tag"), 2)
    self.assertIn("checks: read", workflow)
    self.assertIn("persist-credentials: false", workflow)
    self.assertNotIn("upload-artifact", workflow)
    self.assertNotIn("release: published", workflow)
    regression = (ROOT / ".github/workflows/release-gate-tests.yml").read_text(encoding="utf-8")
    self.assertIn("pull_request:", regression)
    self.assertIn("merge_group:", regression)
    self.assertIn("branches: [main]", regression)
    self.assertIn("name: Release gating regression suite", regression)
    self.assertIn("Release gating regression suite", gate.REQUIRED_CHECKS)


if __name__ == "__main__":
  unittest.main()
