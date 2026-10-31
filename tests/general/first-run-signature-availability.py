#!/usr/bin/env python3
"""First-run signature availability is observational and never authorizes scans."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
WELCOME = ROOT / "PDFMagicOpenerApp/FirstRunWelcomeView.swift"
STATUS = ROOT / "PDFMagicOpenerApp/SignatureUpdateStatus.swift"
TEST = ROOT / "test-first-run-signature-availability.swift"
CI = ROOT / ".github/workflows/ci.yml"


class FirstRunSignatureAvailabilityTests(unittest.TestCase):
  def test_welcome_checks_at_display_time_and_allows_manual_recheck(self):
    source = WELCOME.read_text(encoding="utf-8")
    self.assertIn("FirstRunSignatureAvailability.readInstalled()", source)
    self.assertIn('Label("Signature availability"', source)
    self.assertIn("Text(signatureAvailability.explanation)", source)
    self.assertIn('accessibilityIdentifier("firstRunSignatureAvailability")', source)
    self.assertIn('Button("Check Signature Files Again")', source)
    self.assertIn('accessibilityIdentifier("firstRunRecheckSignatures")', source)
    self.assertNotIn("Process(", source)
    self.assertNotIn("clamscan(", source)
    self.assertNotIn("updateSignatures()", source)

  def test_availability_does_not_claim_validity_or_change_gate(self):
    source = STATUS.read_text(encoding="utf-8")
    section = source.split("enum FirstRunSignatureAvailability: Equatable {", 1)[1]
    for marker in ("main", "daily", ".cvd", ".cld", "lstat(",
                   "S_IFREG", "S_IFDIR", "st_size", ".unsafe",
                   "Validity and freshness are not verified"):
      self.assertIn(marker, section)
    for forbidden in ("Process(", "open(", "Data(contentsOf:", "write(", "subprocess",
                      "last-successful-update", "target-app.txt",
                      "UserDefaults", "clamscan("):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, section)
    self.assertIn("FileManager.default.homeDirectoryForCurrentUser", section)

  def test_native_fixtures_are_isolated_and_ci_runs_both_checks(self):
    fixture = TEST.read_text(encoding="utf-8")
    self.assertIn("temporaryDirectory", fixture)
    self.assertIn("removeItem(at: root)", fixture)
    for status in (".available", ".missing", ".incomplete", ".unsafe"):
      self.assertIn(status, fixture)
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("tests/general/first-run-signature-availability.py -v", ci)
    self.assertIn("test-first-run-signature-availability.swift", ci)
    self.assertIn('"$RUNNER_TEMP/TestFirstRunSignatureAvailability"', ci)


if __name__ == "__main__":
  unittest.main()
