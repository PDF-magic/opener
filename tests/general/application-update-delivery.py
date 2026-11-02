#!/usr/bin/env python3
"""Guard the documented native application update delivery decision."""
from pathlib import Path
import re
import unittest
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs/application-update-delivery.md"


class ApplicationUpdateDeliveryTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = DOC.read_text(encoding="utf-8")

  def test_current_delivery_is_manual_trusted_source(self):
    for required in (
      "user-initiated", "complete trusted checkout", "PDF-magic/opener",
      "no background", "no published binary update channel",
      "bash install-allow-and-open.sh", "normal user", "macOS 13",
      "finish any active scans", "post-install verification",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.guide.lower())
    installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    self.assertIn("scripts/report_install_prerequisites.py", installer)
    self.assertIn('if [ "$EUID" -eq 0 ]; then', installer)

  def test_future_binary_channel_is_gated_and_source_release_is_not_binary(self):
    for required in (
      "Future public delivery decision (not implemented)",
      "signed and notarized application archive",
      "official GitHub Releases", "Developer ID", "checksums",
      "release notes", "vX.Y.Z", "source-only",
      "NOT RELEASE READY", "not a signed/notarized app update",
      "separate approval",
    ):
      with self.subTest(required=required):
        self.assertIn(required, self.guide)
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    gate = (ROOT / "scripts/require_release_checks.py").read_text(encoding="utf-8")
    distribution = (ROOT / "docs/browser-extension-distribution.md").read_text(encoding="utf-8")
    self.assertIn("Publish verified source-only GitHub release", workflow)
    self.assertIn("gh release create", workflow)
    self.assertIn("NOT RELEASE READY", distribution)
    self.assertIn("Distribution remains NOT RELEASE READY", gate)

  def test_app_update_is_not_signature_or_browser_auto_update(self):
    for required in (
      "ClamAV", "48-hour", "FreshClam", "Browser extensions",
      "inactive", "browser-managed", "saved preferences",
      "Finder", "macOS default PDF", "quarantine", "rollback",
      "native messaging", "Gatekeeper",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.guide.lower())
    view = (ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift").read_text(encoding="utf-8")
    self.assertIn("Checking for or installing application updates is not available from this page yet.", view)
    self.assertIn("ManualUpdateActions.updateSignatures()", view)
    self.assertNotIn("downloadTask", view)

  def test_index_and_local_documentation_links(self):
    index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    self.assertIn("(application-update-delivery.md)", index)
    for link in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", self.guide):
      parsed = urlsplit(link)
      if not parsed.scheme and not parsed.netloc and parsed.path:
        with self.subTest(link=link):
          self.assertTrue((DOC.parent / parsed.path).is_file(), link)

  def test_required_ci_runs_policy_regressions(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("python3 tests/general/application-update-delivery.py -v", ci)
    self.assertIn("python3 tests/general/upgrade-documentation.py -v", ci)


if __name__ == "__main__":
  unittest.main()
