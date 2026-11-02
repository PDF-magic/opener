#!/usr/bin/env python3
"""Guard manual source-based macOS updates without binary release channels."""

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
    cls.normalized = re.sub(r"\s+", " ", cls.guide.replace("**", "")).lower()

  def test_manual_trusted_source_and_explicit_installation(self):
    for required in (
      "user-initiated", "complete trusted checkout", "PDF-magic/opener",
      "no background", "no published binary update channel",
      "bash install-allow-and-open.sh", "normal user", "macOS 13",
      "finish any active scans", "post-install verification",
      "upgrade procedure", "rollback",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.normalized)
    installer = (ROOT / "install-allow-and-open.sh").read_text(encoding="utf-8")
    self.assertIn("scripts/report_install_prerequisites.py", installer)
    self.assertIn('if [ "$EUID" -eq 0 ]; then', installer)

  def test_no_binary_distribution_signing_or_updater_is_planned(self):
    for required in (
      "No prebuilt release or signing plan",
      "does not establish GitHub Releases distribution",
      "no signing or notarization pipeline is planned",
      "source-based installation procedure is development-only",
      "not the installation or update channel",
      "NOT RELEASE READY", "separate approval", "Gatekeeper",
      "do not bypass Gatekeeper",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.normalized)
    for forbidden in (
      "intended public native macOS application delivery channel",
      "official GitHub Releases", "future public delivery decision",
      "browser-managed update requirements",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden.lower(), self.normalized)
    self.assertIn("no background application updater", self.normalized)
    self.assertIn("no published binary update channel", self.normalized)

  def test_app_update_preserves_security_and_separate_update_streams(self):
    for required in (
      "ClamAV", "48-hour", "FreshClam", "Browser extensions",
      "inactive", "manual unpacked reloads", "saved preferences",
      "Finder", "macOS default PDF", "quarantine", "rollback",
      "native messaging", "scan-before-open",
      "file-integrity", "signature", "Gatekeeper",
    ):
      with self.subTest(required=required):
        self.assertIn(required.lower(), self.normalized)
    view = (ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift").read_text(encoding="utf-8")
    self.assertIn(
      "Checking for or installing application updates is not available from this page yet.",
      view,
    )
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
