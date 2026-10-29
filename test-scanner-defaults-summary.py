#!/usr/bin/env python3
"""opener-0402: scanner defaults are visible before advanced information."""
from pathlib import Path
import unittest

from scanner_argument_validation import validated_file_size_options

ROOT = Path(__file__).resolve().parent
PAGE = ROOT / "PDFMagicOpenerApp" / "AdvancedScanningSettingsView.swift"


class ScannerDefaultsSummaryTests(unittest.TestCase):
  def test_defaults_are_visible_and_precede_all_advanced_sections(self):
    source = PAGE.read_text(encoding="utf-8")
    start = source.index('Label("Built-in scanner defaults"')
    self.assertIn('accessibilityIdentifier("advancedScanningDefaultsSection")', source)
    for section in ('"Malware scanning"', '"File readiness"', '"Scan results"'):
      with self.subTest(section=section):
        self.assertLess(start, source.index(section))
    for label in (
        'LabeledContent("Scanner", value: "ClamAV checks files locally before opening")',
        'LabeledContent("PDF scan timeout", value: "30 minutes")',
        'LabeledContent("Other-file scan timeout", value: "3 minutes")',
        'LabeledContent("Non-PDF file limit", value: "512 MB per file")',
        'LabeledContent("Required signatures", value: "main and daily; checked within 48 hours")',
    ):
      with self.subTest(default=label):
        self.assertIn(label, source)

  def test_presented_limits_match_the_real_fail_closed_gate(self):
    source = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    argv = (ROOT / "scanner_argument_validation.py").read_text(encoding="utf-8")
    for contract in (
        "PDF_SCAN_TIMEOUT = 30 * 60",
        "MAX_FILE_SIZE = 512 * 1024 * 1024",
        "MAX_DATABASE_AGE = 48 * 60 * 60",
        "other_timeout_seconds: int = 180",
        "if not has_signature_file('daily') or not has_signature_file('main'):",
        "size > MAX_FILE_SIZE and (is_bundle or path.suffix.lower() != '.pdf')",
    ):
      with self.subTest(contract=contract):
        self.assertIn(contract, source)
    self.assertEqual(
        validated_file_size_options(is_pdf=False),
        ("--max-filesize=512M", "--max-scansize=1024M"),
    )
    self.assertEqual(
        validated_file_size_options(is_pdf=True),
        ("--max-filesize=0", "--max-scansize=0"),
    )
    self.assertIn('"--alert-exceeds-max=yes"', argv)
    self.assertIn('"--alert-encrypted=yes"', argv)

  def test_defaults_remain_read_only_and_preserve_custom_choices(self):
    source = PAGE.read_text(encoding="utf-8")
    self.assertIn("does not change scanner behavior or reset saved choices", source)
    self.assertIn("Advanced scanner parameters are not editable here.", source)
    # The defaults summary is informational. A separately confirmed
    # "Restore Recommended Limits" action elsewhere on this page is valid.
    start = source.index("        // Reference values from the mandatory Built-in scan gate")
    end = source.index('accessibilityIdentifier("advancedScanningDefaultsSection")')
    defaults_section = source[start:end]
    for forbidden in (
        "Toggle(", "Button(", "Picker(", "Slider(", "@AppStorage",
        "UserDefaults", "Process(", "FileHandle(", "NSWorkspace",
        "write(to:", "createFile(", "clamscan(", "target-app.txt",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, defaults_section)

  def test_both_ci_jobs_verify_the_defaults_summary(self):
    source = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    command = "python3 test-scanner-defaults-summary.py -v"
    self.assertEqual(source.count(command), 2)
    self.assertLess(source.index(command), source.index("  macos-build:"))
    self.assertGreater(source.rindex(command), source.index("  macos-build:"))


if __name__ == "__main__":
  unittest.main()
