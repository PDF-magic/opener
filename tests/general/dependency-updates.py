#!/usr/bin/env python3
"""Read-only checks for documented dependency updates (opener-1160)."""

import ast
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "docs/dependency-update-policy.md"


class DependencyUpdatePolicyTests(unittest.TestCase):
  def test_policy_covers_real_update_owners_and_review_gates(self):
    content = POLICY.read_text(encoding="utf-8")
    for term in (
      "ClamAV", "Externally managed by the user", "Homebrew",
      "freshclam", "four hours", "48-hour", "private staging",
      "Native Swift", "reviewed helper", "requirements-enhanced-pdf.txt",
      "docs/dependency-licenses.json", "CI-only", "pypdf",
      "WebExtension", "no npm dependencies", "GitHub Actions",
      "At least monthly", "Every Monday", "security advisories",
      "reviewed PR", "transitive dependencies", "rollback",
      "release gate", "fail", "user preferences",
    ):
      with self.subTest(term=term):
        self.assertIn(term.lower(), content.lower())

  def test_documentation_is_discoverable_and_links_resolve(self):
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    self.assertIn("[Dependency update policy](dependency-update-policy.md)", index)
    content = POLICY.read_text(encoding="utf-8")
    for target in re.findall(r"\]\(([^)#]+\.md)(?:#[^)]*)?\)", content):
      with self.subTest(target=target):
        self.assertTrue((POLICY.parent / target).is_file(), target)

  def test_policy_matches_external_scanner_and_separate_signature_updates(self):
    source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    paths = next(node.value for node in tree.body
                 if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name)
                         and target.id == "CLAMAV_CANDIDATES"
                         for target in node.targets))
    self.assertEqual(ast.literal_eval(paths), (
      "/opt/homebrew/bin/clamscan",
      "/usr/local/bin/clamscan",
      "/usr/local/clamav/bin/clamscan",
    ))
    self.assertIn("require_supported_scanner_version(scanner)", source)
    installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    self.assertIn("HOMEBREW_NO_AUTO_UPDATE=1", installer)
    self.assertIn("confirm_clamav_install.py", installer)
    updater = (ROOT / "update-malware-signatures.sh").read_text(encoding="utf-8")
    self.assertIn('run_freshclam_with_network_recovery "$updater"', updater)
    self.assertIn('"$stage_dir" "$signature_dir"', updater)
    self.assertIn("Another signature update is running", updater)

  def test_optional_parser_is_pinned_and_webextension_has_no_packages(self):
    requirements = (ROOT / "requirements-enhanced-pdf.txt").read_text(encoding="utf-8")
    pins = [line.strip() for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
    self.assertEqual(len(pins), 1)
    self.assertRegex(pins[0], r"^pypdf==\d+\.\d+\.\d+$")
    package = json.loads((ROOT / "extensions/webextension/package.json").read_text())
    for field in ("dependencies", "devDependencies",
                  "optionalDependencies", "peerDependencies"):
      self.assertFalse(package.get(field), field)
    self.assertIn("scripts/check_dependency_licenses.py",
                  POLICY.read_text(encoding="utf-8"))

  def test_required_ci_checks_policy_and_keeps_existing_vulnerability_audit(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("PYTHONPATH=. python3 tests/general/dependency-updates.py -v", ci)
    self.assertIn("python3 scripts/check_dependency_licenses.py", ci)
    audit = (ROOT / ".github/workflows/dependency-vulnerabilities.yml").read_text()
    self.assertIn("pull_request:", audit)
    self.assertIn("schedule:", audit)
    self.assertIn("pip-audit --strict", audit)
    self.assertIn("--kind current", audit)
    self.assertIn("--kind legacy", audit)


if __name__ == "__main__":
  unittest.main()
