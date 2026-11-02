#!/usr/bin/env python3
"""Hermetic dependency upgrade regression tests (opener-1168).

Exercise the existing license-review and vulnerability gates against a
synthetic upgrade. Never install packages, run a scanner, or change live files.
"""

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import check_dependency_licenses as licenses
import dependency_vulnerability_audit as audit


class DependencyUpdateRegressionTests(unittest.TestCase):
  def setUp(self):
    temporary = tempfile.TemporaryDirectory(prefix="opener-dependency-upgrade-")
    self.addCleanup(temporary.cleanup)
    self.root = Path(temporary.name)
    for path in (licenses.INVENTORY, licenses.REQUIREMENTS,
                 licenses.BROWSER_PACKAGE, "LICENSE", "install-allow-and-open.sh"):
      destination = self.root / path
      destination.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(ROOT / path, destination)
    workflows = self.root / ".github/workflows"
    workflows.mkdir(parents=True)
    for workflow in (ROOT / ".github/workflows").glob("*.yml"):
      shutil.copyfile(workflow, workflows / workflow.name)
    self.active = next(
      line.strip().split("==", 1)[1]
      for line in (self.root / licenses.REQUIREMENTS).read_text().splitlines()
      if line.strip() and not line.lstrip().startswith("#")
    )
    self.new_version = "99.99.99" if self.active != "99.99.99" else "99.99.98"

  def replace(self, path, old, new):
    target = self.root / path
    content = target.read_text(encoding="utf-8")
    self.assertIn(old, content, path)
    target.write_text(content.replace(old, new, 1), encoding="utf-8")

  def update_inventory(self):
    path = self.root / licenses.INVENTORY
    data = json.loads(path.read_text(encoding="utf-8"))
    versions = data["pypdf"]["versions"]
    self.assertIn(self.active, versions)
    data["pypdf"]["versions"] = [
      self.new_version if value == self.active else value for value in versions
    ]
    path.write_text(json.dumps(data), encoding="utf-8")

  def reviewed_versions(self):
    versions, license_expression = licenses.REVIEWED["pypdf"]
    self.assertIn(self.active, versions)
    return tuple(
      self.new_version if value == self.active else value for value in versions
    ), license_expression

  def test_baseline_is_consistent_and_does_not_mutate_inputs(self):
    original = {
      relative: (self.root / relative).read_bytes()
      for relative in (licenses.INVENTORY, licenses.REQUIREMENTS,
                       licenses.BROWSER_PACKAGE)
    }
    reviewed = licenses.check(self.root)
    self.assertIn(("pypdf", self.active), reviewed)
    self.assertEqual(audit.pins(self.root)[0], {("pypdf", self.active)})
    for path, before in original.items():
      self.assertEqual((self.root / path).read_bytes(), before)

  def test_parser_pin_alone_is_rejected(self):
    self.replace(licenses.REQUIREMENTS,
                 "pypdf==" + self.active, "pypdf==" + self.new_version)
    with self.assertRaises(licenses.LicenseReviewError):
      licenses.check(self.root)
    with self.assertRaises(licenses.LicenseReviewError):
      audit.create_manifests(self.root / "manifests", self.root)

  def test_inventory_and_pin_without_explicit_review_are_rejected(self):
    self.replace(licenses.REQUIREMENTS,
                 "pypdf==" + self.active, "pypdf==" + self.new_version)
    self.update_inventory()
    with self.assertRaises(licenses.LicenseReviewError):
      licenses.check(self.root)

  def test_review_registry_without_matching_inventory_is_rejected(self):
    reviewed_versions, license_expression = self.reviewed_versions()
    with mock.patch.dict(licenses.REVIEWED, {
      "pypdf": (reviewed_versions, license_expression),
    }):
      with self.assertRaises(licenses.LicenseReviewError):
        licenses.check(self.root)

  def test_coordinated_upgrade_updates_audit_manifest_and_blocks_advisories(self):
    self.replace(licenses.REQUIREMENTS,
                 "pypdf==" + self.active, "pypdf==" + self.new_version)
    self.update_inventory()
    reviewed_versions, license_expression = self.reviewed_versions()
    with mock.patch.dict(licenses.REVIEWED, {
      "pypdf": (reviewed_versions, license_expression),
    }):
      self.assertIn(("pypdf", self.new_version), licenses.check(self.root))
      current, renderer, legacy = audit.create_manifests(
        self.root / "manifests", self.root)
      self.assertEqual(current, {("pypdf", self.new_version)})
      self.assertEqual(renderer, {("pymupdf", licenses.REVIEWED["pymupdf"][0][0])})
      self.assertNotIn(("pypdf", self.active), current)
      self.assertNotIn(("pypdf", self.active), legacy)
      manifest = (self.root / "manifests/current.txt").read_text()
      self.assertEqual(manifest, "pypdf==" + self.new_version + "\n")

      report = self.root / "report.json"
      report.write_text(json.dumps({"dependencies": [{
        "name": "pypdf", "version": self.active, "vulns": [],
      }]}))
      with self.assertRaises(audit.VulnerabilityAuditError):
        audit.verify_report(report, current, 0, True)
      report.write_text(json.dumps({"dependencies": [{
        "name": "pypdf", "version": self.new_version, "vulns": [],
      }]}))
      self.assertEqual(audit.verify_report(report, current, 0, True), 0)
      report.write_text(json.dumps({"dependencies": [{
        "name": "pypdf", "version": self.new_version,
        "vulns": [{"id": "GHSA-test-upgrade"}],
      }]}))
      with self.assertRaises(audit.VulnerabilityAuditError):
        audit.verify_report(report, current, 1, True)

  def test_ci_tool_update_requires_review(self):
    version = licenses.REVIEWED["ruff"][0][0]
    self.replace(".github/workflows/source-lint.yml",
                 "ruff==" + version, "ruff==99.99.99")
    with self.assertRaises(licenses.LicenseReviewError):
      licenses.check(self.root)

  def test_extension_dependency_addition_requires_review(self):
    path = self.root / licenses.BROWSER_PACKAGE
    package = json.loads(path.read_text())
    package["dependencies"] = {"unreviewed-test": "1.0.0"}
    path.write_text(json.dumps(package))
    with self.assertRaises(licenses.LicenseReviewError):
      licenses.check(self.root)

  def test_required_ci_runs_regressions_and_preserves_audit(self):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("PYTHONPATH=. python3 tests/dependencies/update-regressions.py -v",
                  workflow)
    self.assertIn("PYTHONPATH=. python3 tests/general/dependency-updates.py -v",
                  workflow)
    audit_ci = (ROOT / ".github/workflows/dependency-vulnerabilities.yml").read_text()
    for required in ("pull_request:", "merge_group:", "schedule:",
                     "--kind current", "--kind renderer", "--kind legacy"):
      self.assertIn(required, audit_ci)


if __name__ == "__main__":
  unittest.main()
