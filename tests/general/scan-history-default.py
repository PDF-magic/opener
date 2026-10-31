#!/usr/bin/env python3
"""Guard opener-0900's opt-in-only decision for optional local scan history."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "PDFMagicOpenerApp" / "PrivacyAndLogsSettingsView.swift"
DOC = ROOT / "docs" / "scan-history-default.md"
README = ROOT / "README.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class ScanHistoryDefaultTests(unittest.TestCase):
  def test_privacy_page_states_off_default_and_missing_implementation(self):
    page = PAGE.read_text(encoding="utf-8")
    self.assertIn('GroupBox("Optional local scan history")', page)
    section = page.split('GroupBox("Optional local scan history")', 1)[1]
    section = section.split('GroupBox("Privacy and log controls")', 1)[0]
    for required in (
      '"Off by default"',
      "scan history is off by default",
      "is not implemented in this version",
      "No scan-history opt-in control or store is provided here",
      "operational scan records and the clean-scan cache are separate",
      'accessibilityIdentifier("optionalScanHistorySection")',
    ):
      with self.subTest(required=required):
        self.assertIn(required, section)

  def test_page_remains_informational_and_side_effect_free(self):
    page = PAGE.read_text(encoding="utf-8")
    for forbidden in (
      "Toggle(", "Picker(", "@AppStorage", "UserDefaults",
      "FileManager", "FileHandle", "Process(", "write(to:", "createFile(",
      "removeItem(", "NSWorkspace", "URLSession", "clamscan(",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, page)
    self.assertIn("This page does not read, display, export, or clear log files.", page)
    self.assertIn('Button("Show recent scan results")', page)
    self.assertIn("recentScanHistory = RecentScanHistoryReader.load()", page)
    self.assertNotIn(".onAppear", page)
    self.assertIn("Viewing this page leaves active scans, quarantine safeguards", page)

  def test_documented_default_requires_opt_in_and_preserves_existing_cache(self):
    doc = DOC.read_text(encoding="utf-8")
    readme = README.read_text(encoding="utf-8")
    for required in (
      "off by default", "explicit, informed", "Absence of a saved choice",
      "90-day clean-scan cache", "operational scan-request",
      "not", "malware", "quarantine", "have **not** been implemented",
    ):
      with self.subTest(required=required):
        self.assertIn(required, doc)
    self.assertIn("Optional local scan history (opener-0900)", readme)
    self.assertIn("docs/scan-history-default.md", readme)
    self.assertIn("The default is **off**.", readme)

  def test_contract_runs_in_required_ci(self):
    ci = CI.read_text(encoding="utf-8")
    self.assertIn(
      "PYTHONPATH=. python3 tests/general/scan-history-default.py -v", ci
    )
    self.assertIn("scanner-tests:", ci)
    self.assertIn("macos-build:", ci)


if __name__ == "__main__":
  unittest.main()
