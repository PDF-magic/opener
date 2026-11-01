#!/usr/bin/env python3
"""Deterministic tests for dependency vulnerability audit coverage (opener-1100)."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "dependency_vulnerability_audit", ROOT / "scripts/dependency_vulnerability_audit.py")
# The audit script imports the existing scripts directory's licensing gate.
import sys
sys.path.insert(0, str(ROOT / "scripts"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DependencyVulnerabilityTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory(prefix="opener-vulnerabilities-")
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    self.expected = {("pypdf", "6.21.3")}
    self.report = self.root / "report.json"

  def write_report(self, dependencies):
    self.report.write_text(json.dumps({"dependencies": dependencies}), encoding="utf-8")

  def package(self, name="pypdf", version="6.21.3", vulns=None):
    return {"name": name, "version": version, "vulns": vulns or []}

  def test_current_and_legacy_pins_come_from_license_review(self):
    (self.root / "requirements-enhanced-pdf.txt").write_text("# optional\npypdf==6.21.3\n")
    versions = {("pypdf", "6.21.3"), ("pypdf", "5.9.0"),
                ("Pillow", "11.3.0"), ("cryptography", "46.0.4")}
    with mock.patch.object(audit.licenses, "check", return_value=versions):
      current, legacy = audit.create_manifests(self.root / "manifests", self.root)
    self.assertEqual(current, {("pypdf", "6.21.3")})
    self.assertEqual(legacy, {("pypdf", "5.9.0"), ("pillow", "11.3.0"),
                              ("cryptography", "46.0.4")})
    self.assertEqual((self.root / "manifests/current.txt").read_text(), "pypdf==6.21.3\n")
    self.assertIn("cryptography==46.0.4", (self.root / "manifests/legacy.txt").read_text())

  def test_clean_scan_passes(self):
    self.write_report([self.package()])
    self.assertEqual(audit.verify_report(self.report, self.expected, 0, True), 0)

  def test_current_advisory_fails_even_with_scanner_exit_one(self):
    self.write_report([self.package(vulns=[{"id": "GHSA-aaaa-bbbb-cccc"}])])
    with self.assertRaises(audit.VulnerabilityAuditError):
      audit.verify_report(self.report, self.expected, 1, True)

  def test_legacy_known_advisory_is_reported_not_silenced(self):
    self.write_report([self.package(vulns=[{"id": "CVE-2026-0001"}])])
    self.assertEqual(audit.verify_report(self.report, self.expected, 1, False), 1)

  def test_missing_package_wrong_version_and_duplicate_fail(self):
    for entries in ([], [self.package(version="6.21.4")],
                    [self.package(), self.package()]):
      with self.subTest(entries=entries):
        self.write_report(entries)
        with self.assertRaises(audit.VulnerabilityAuditError):
          audit.verify_report(self.report, self.expected, 0, True)

  def test_invalid_schema_and_malformed_advisories_fail(self):
    for data in ("{}", '{"dependencies": "oops"}', "not json"):
      self.report.write_text(data)
      with self.assertRaises(audit.VulnerabilityAuditError):
        audit.verify_report(self.report, self.expected, 0, True)
    self.write_report([self.package(vulns=[{"unexpected": "data"}])])
    with self.assertRaises(audit.VulnerabilityAuditError):
      audit.verify_report(self.report, self.expected, 1, True)

  def test_scanner_error_and_status_mismatch_fail_closed(self):
    self.write_report([self.package()])
    for status in (1, 2, 127):
      with self.subTest(status=status), self.assertRaises(audit.VulnerabilityAuditError):
        audit.verify_report(self.report, self.expected, status, False)
    self.report.unlink()
    with self.assertRaises(audit.VulnerabilityAuditError):
      audit.verify_report(self.report, self.expected, 0, False)

  def test_unreviewed_active_pin_is_rejected(self):
    (self.root / "requirements-enhanced-pdf.txt").write_text("other==9.9\n")
    with mock.patch.object(audit.licenses, "check", return_value=self.expected):
      with self.assertRaises(audit.VulnerabilityAuditError):
        audit.pins(self.root)


if __name__ == "__main__":
  unittest.main()
