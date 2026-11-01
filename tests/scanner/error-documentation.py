#!/usr/bin/env python3
"""Ensure the scanner-error guide matches the trusted fail-closed policy."""

from pathlib import Path
import re
import unittest

from scan_results import ScanResultStatus
from scanner_failure_policy import (
  SCANNER_FAILURE_RESPONSES,
  UNKNOWN_SCANNER_FAILURE_RESPONSE,
  ScannerFailureKind,
)

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs/scanner/errors.md"
INDEX = ROOT / "docs/README.md"
GATE = ROOT / "scan-and-open.py"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


class ScannerErrorDocumentationTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.guide = GUIDE.read_text(encoding="utf-8")
    cls.gate = GATE.read_text(encoding="utf-8")

  def test_every_failure_kind_has_its_exact_canonical_status_and_message(self):
    section = self.guide.split("## Scanner error types\n", 1)[1].split("\n## ", 1)[0]
    rows = {}
    for kind, status, message in re.findall(
      r"^\| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", section, re.MULTILINE
    ):
      key = kind.strip().strip(chr(96))
      if key in {item.value for item in ScannerFailureKind} | {"unknown/untrusted"}:
        self.assertNotIn(key, rows)
        rows[key] = (status.strip().strip(chr(96)), message.strip())

    expected = {
      kind.value: (response.scan_status.value, response.user_message)
      for kind, response in SCANNER_FAILURE_RESPONSES.items()
    }
    expected["unknown/untrusted"] = (
      UNKNOWN_SCANNER_FAILURE_RESPONSE.scan_status.value,
      UNKNOWN_SCANNER_FAILURE_RESPONSE.user_message,
    )
    self.assertEqual(rows, expected)
    self.assertEqual(set(SCANNER_FAILURE_RESPONSES), set(ScannerFailureKind))
    for kind, response in SCANNER_FAILURE_RESPONSES.items():
      with self.subTest(kind=kind.value):
        self.assertNotEqual(response.scan_status, ScanResultStatus.clean)
        self.assertFalse(response.allow_open)
        self.assertFalse(response.allow_fallback)
        self.assertFalse(response.allow_override)
        self.assertFalse(response.retry_automatically)
        self.assertTrue(response.preserve_quarantine)

  def test_guidance_matches_installed_scan_gate(self):
    for source in (
      "def decide_opening(detection):",
      "if detection.exit_code != 0:",
      "_CLAMAV_DIAGNOSTIC_LINE",
      "def check_database():",
      "MAX_DATABASE_AGE = 48 * 60 * 60",
      "def safe_scan_failure(error):",
      "def require_supported_scanner_version(scanner):",
      "1\\.(?:4|5)",
    ):
      with self.subTest(source=source):
        self.assertIn(source, self.gate)
    for statement in (
      "Built-in ClamAV", "not** mean malware was confirmed",
      "initializationFailed", "incompleteScan", "scanTimedOut",
      "nonzero ClamAV exit", "Even exit code zero",
      "48 hours", "1.4 or 1.5", "update-malware-signatures.sh",
      "path-free", "unopened and quarantined", "clean-cache",
      "new user-initiated", "no automatic retry", "no",
      "Show\nBlocked File Notifications", "off by default",
      "preview-only/non-selectable", "documentation only",
    ):
      with self.subTest(statement=statement):
        self.assertIn(statement, self.guide)

  def test_links_and_required_ci_integration(self):
    self.assertIn(
      "[Scanner errors and recovery](scanner/errors.md)",
      INDEX.read_text(encoding="utf-8"),
    )
    for target in re.findall(r"\]\(([^)]+)\)", self.guide):
      if "://" not in target and not target.startswith("#"):
        with self.subTest(target=target):
          self.assertTrue((GUIDE.parent / target.split("#", 1)[0]).is_file())
    self.assertIn(
      "PYTHONPATH=. python3 tests/scanner/error-documentation.py -v",
      WORKFLOW.read_text(encoding="utf-8"),
    )


if __name__ == "__main__":
  unittest.main()
