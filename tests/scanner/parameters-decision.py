#!/usr/bin/env python3
"""opener-0397: fixed scanner arguments are not user-editable."""

from pathlib import Path
import unittest

from scanner_argument_validation import (
    InvalidScannerArguments,
    validate_scanner_arguments,
    validated_file_size_options,
)

ROOT = Path(__file__).resolve().parent


class ScannerParameterDecisionTests(unittest.TestCase):
    def test_both_modes_reject_arbitrary_or_weakened_options(self):
        scanner = "/opt/homebrew/bin/clamscan"
        database = Path("/tmp/test-signature database")
        document = Path("/tmp/-file --exclude-me.pdf")
        for is_pdf in (True, False):
            size = (
                ("--max-filesize=0", "--max-scansize=0") if is_pdf
                else ("--max-filesize=512M", "--max-scansize=1024M")
            )
            command = [
                scanner, "--database=" + str(database), "--recursive",
                "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
                "--alert-exceeds-max=yes", "--alert-encrypted=yes",
                *size, "--max-scantime=0", "--no-summary", "--",
                str(document),
            ]
            args = {
                "scanner": scanner, "database": database,
                "document": document, "is_pdf": is_pdf,
                "timeout": 1800 if is_pdf else 180,
            }
            validate_scanner_arguments(command, **args)
            self.assertEqual(command[-2:], ["--", str(document)])
            attempts = [
                command[:-2] + ["--exclude=*", *command[-2:]],
                command[:6] + ["--alert-encrypted=no", *command[7:]],
                command[:7] + ["--max-filesize=512M" if is_pdf else "--max-filesize=0", *command[8:]],
                command[:1] + ["--database=/tmp/other", *command[2:]],
                command[:-2] + [str(document), "--"],
            ]
            for attempt in attempts:
                with self.subTest(is_pdf=is_pdf, command=attempt):
                    with self.assertRaises(InvalidScannerArguments):
                        validate_scanner_arguments(attempt, **args)

    def test_scan_gate_validates_fixed_flags_before_scanner_execution(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        validator = (ROOT / "scanner_argument_validation.py").read_text(
            encoding="utf-8"
        )
        # The active gate now obtains fixed size arguments from the shared
        # validator, so verify the exact options instead of stale literals.
        self.assertIn("size_options = validated_file_size_options(is_pdf=is_pdf)", scanner)
        self.assertEqual(validated_file_size_options(is_pdf=True),
                         ("--max-filesize=0", "--max-scansize=0"))
        self.assertEqual(validated_file_size_options(is_pdf=False),
                         ("--max-filesize=512M", "--max-scansize=1024M"))
        self.assertIn("size_options = validated_file_size_options(is_pdf=is_pdf)", validator)
        for phrase in (
            "'--alert-exceeds-max=yes', '--alert-encrypted=yes'",
            "'--max-scantime=0', '--no-summary', '--', str(path)",
            "validate_scanner_arguments(command, scanner=scanner,",
        ):
            self.assertIn(phrase, scanner)
        self.assertIn("_exact_arguments(command, expected)", validator)

    def test_advanced_scanning_discloses_decision_without_editing(self):
        page = (ROOT / "PDFMagicOpenerApp" /
                "AdvancedScanningSettingsView.swift").read_text(encoding="utf-8")
        self.assertIn("Scanner parameters are not user-editable", page)
        self.assertIn("your saved choices remain unchanged", page)
        # The sole allowed action clears optional metadata after confirmation,
        # not an executable ClamAV parameter or scanner control.
        self.assertEqual(page.count('Button("Restore Recommended Limits"'), 2)
        self.assertIn("RecommendedScannerLimitsReset.restore()", page)
        for term in (
            "TextField(", "SecureField(", "Toggle(", "Picker(", "Slider(",
            "Stepper(", "@AppStorage", "UserDefaults",
            "Process(", "write(to:", "run_scan_command(",
        ):
            with self.subTest(control=term):
                self.assertNotIn(term, page)

    def test_policy_and_ci_are_present(self):
        doc = (ROOT / "docs" / "scanner/parameters-decision.md").read_text(
            encoding="utf-8"
        )
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for term in (
            "Decision: scanner parameters are not user-editable",
            "scanner_argument_validation.py", "saved",
            "When to reconsider",
        ):
            self.assertIn(term, doc)
        self.assertIn("docs/scanner/parameters-decision.md", readme)
        self.assertIn("python3 test-scanner-parameters-decision.py -v", ci)
        self.assertIn("python3 test-scanner-arguments.py -v", ci)


if __name__ == "__main__":
    unittest.main()
