#!/usr/bin/env python3
"""Regression tests for offline dependency licensing review (opener-0959)."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_dependency_licenses.py"
spec = importlib.util.spec_from_file_location("check_dependency_licenses", CHECK)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class DependencyLicensingTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory(prefix="opener-licenses-")
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    for path in (checker.INVENTORY, checker.REQUIREMENTS,
                 checker.BROWSER_PACKAGE, "LICENSE", "install-allow-and-open.sh"):
      destination = self.root / path
      destination.parent.mkdir(parents=True, exist_ok=True)
      shutil.copyfile(ROOT / path, destination)
    workflows = self.root / ".github/workflows"
    workflows.mkdir(parents=True)
    for path in (ROOT / ".github/workflows").glob("*.yml"):
      shutil.copyfile(path, workflows / path.name)

  def edit(self, path, old, new):
    target = self.root / path
    content = target.read_text()
    self.assertIn(old, content)
    target.write_text(content.replace(old, new, 1))

  def test_review_passes_for_current_pins_and_is_read_only(self):
    manifest = self.root / checker.INVENTORY
    before = manifest.read_bytes()
    found = checker.check(self.root)
    self.assertIn(("pypdf", "6.21.3"), found)
    self.assertIn(("pypdf", "5.9.0"), found)
    self.assertIn(("pymupdf", "2.0"), found)
    self.assertEqual(manifest.read_bytes(), before)

  def test_reject_unreviewed_dependency_and_unpinned_install(self):
    workflow = ".github/workflows/ci.yml"
    original = "pip install --disable-pip-version-check -r requirements-enhanced-pdf.txt"
    changed = original + " brandnew==1.0"
    self.edit(workflow, original, changed)
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)
    self.edit(workflow, changed, original)
    self.edit(workflow, "requirements-enhanced-pdf.txt", "unreviewed-package")
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)

  def test_rejects_changed_version_even_if_json_is_updated(self):
    self.edit(checker.REQUIREMENTS, "pypdf==6.21.3", "pypdf==999.1")
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)

  def test_rejects_missing_or_altered_license_evidence(self):
    path = self.root / checker.INVENTORY
    records = json.loads(path.read_text())
    records["clamav"]["license"] = "MIT"
    path.write_text(json.dumps(records))
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)
    records["clamav"]["license"] = "GPL-2.0-only"
    del records["pymupdf"]["distribution_requirements"]
    path.write_text(json.dumps(records))
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)

  def test_rejects_new_webextension_runtime_dependency(self):
    path = self.root / checker.BROWSER_PACKAGE
    package = json.loads(path.read_text())
    package["dependencies"] = {"some-package": "1.2.3"}
    path.write_text(json.dumps(package))
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)

  def test_rejects_unknown_pip_flags_or_unreviewed_requirements(self):
    workflow = ".github/workflows/ci.yml"
    self.edit(workflow, "--disable-pip-version-check", "--upgrade --disable-pip-version-check")
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)
    self.edit(workflow, "--upgrade ", "")
    self.edit(workflow, "requirements-enhanced-pdf.txt", "../something.txt")
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)

  def test_rejects_install_route_or_project_license_changes(self):
    self.edit("install-allow-and-open.sh", "brew install clamav", "brew install unrelated")
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)
    self.edit("install-allow-and-open.sh", "brew install unrelated", "brew install clamav")
    self.edit("LICENSE", "GNU AFFERO GENERAL PUBLIC LICENSE", "INCOMPATIBLE LICENSE")
    with self.assertRaises(checker.LicenseReviewError):
      checker.check(self.root)

  def test_ci_uses_license_gate(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 scripts/check_dependency_licenses.py", ci)
    self.assertIn("python3 tests/general/dependency-licensing.py -v", ci)


if __name__ == "__main__":
  unittest.main()
