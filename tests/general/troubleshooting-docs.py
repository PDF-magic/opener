#!/usr/bin/env python3
"""Keep troubleshooting advice discoverable and aligned with the installed safety gate."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/troubleshooting.md"


class TroubleshootingDocsTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = GUIDE.read_text(encoding="utf-8")
    cls.index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
    cls.ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    cls.scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")

  def test_discoverable_and_registered_in_required_ci(self):
    self.assertIn("(troubleshooting.md)", self.index)
    self.assertIn("tests/general/troubleshooting-docs.py -v", self.ci)
    self.assertRegex(self.guide, r"(?m)^# Troubleshooting PDF Magic Opener$")
    self.assertRegex(self.guide, r"(?m)^## Common symptoms and safe next steps$")
    self.assertRegex(self.guide, r"(?m)^## Repair a damaged installation$")

  def test_local_guide_links_resolve(self):
    for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", self.guide):
      url = target.split("#", 1)[0]
      if not url or "://" in url:
        continue
      with self.subTest(target=target):
        self.assertTrue((GUIDE.parent / url).is_file(), target)

  def test_real_diagnostics_and_recovery_paths(self):
    references = (
      ("install-allow-and-open.sh", "install-allow-and-open.sh"),
      ("Repair Installation.command", "Repair Installation.command"),
      ("update-malware-signatures.sh", "update-malware-signatures.sh"),
      ("pdf-handler-status.py", "pdf-handler-status.py"),
      ("select-browser.md", "docs/select-browser.md"),
      ("browser-unsupported-routes.md", "docs/browser-unsupported-routes.md"),
    )
    for phrase, file in references:
      with self.subTest(phrase=phrase):
        self.assertIn(phrase, self.guide)
        self.assertTrue((ROOT / file).is_file(), file)
    self.assertIn("Run update-malware-signatures.sh.", self.scanner)
    self.assertIn("com.apple.quarantine", self.scanner)

  def test_documented_failure_cases_cannot_be_mistaken_for_clean(self):
    for phrase in (
      "ClamAV is missing", "48 hours", "detected malware",
      "scan fails, times out, is incomplete", "document changed",
      "Double-clicking a local PDF", "viewer is missing",
      "opened inside a browser", "No automatic retry",
      "quarantine", "no fallback", "default PDF handler",
      "post-scan browser", "user preferences", "sudo",
    ):
      with self.subTest(phrase=phrase):
        self.assertIn(phrase.lower(), self.guide.lower())
    self.assertNotIn("disable Gatekeeper to open", self.guide)
    self.assertNotIn("remove quarantine to open", self.guide)


if __name__ == "__main__":
  unittest.main()
