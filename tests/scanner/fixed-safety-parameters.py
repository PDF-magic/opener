#!/usr/bin/env python3
"""opener-0398: audit mandatory scanner safety parameters without changing settings."""

import importlib.util
from pathlib import Path
import unittest

from scanner_argument_validation import (
    InvalidScannerArguments,
    validate_scanner_arguments,
    validate_scanner_version_arguments,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("fixed_safety_scan_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

FIXED_FLAGS = (
    "--recursive", "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
    "--alert-exceeds-max=yes", "--alert-encrypted=yes", "--max-scantime=0",
    "--no-summary", "--",
)


class ScannerFixedSafetyParameterTests(unittest.TestCase):
    def command(self, is_pdf):
        size_flags = ("--max-filesize=0", "--max-scansize=0") if is_pdf else (
            "--max-filesize=512M", "--max-scansize=1024M"
        )
        return [
            "/opt/homebrew/bin/clamscan", "--database=/private/signature database",
            *FIXED_FLAGS[:5], *size_flags, *FIXED_FLAGS[5:],
            "/private/report --alert-encrypted=no.pdf",
        ]

    def check(self, argv, is_pdf):
        validate_scanner_arguments(
            argv, scanner="/opt/homebrew/bin/clamscan",
            database=Path("/private/signature database"),
            document=Path("/private/report --alert-encrypted=no.pdf"),
            is_pdf=is_pdf,
            timeout=gate.PDF_SCAN_TIMEOUT if is_pdf else 180,
        )

    def test_two_modes_require_the_exact_command(self):
        for is_pdf in (True, False):
            with self.subTest(is_pdf=is_pdf):
                argv = self.command(is_pdf)
                self.check(argv, is_pdf)
                self.assertEqual(argv[-2:], ["--", "/private/report --alert-encrypted=no.pdf"])
                with self.assertRaises(InvalidScannerArguments):
                    self.check(argv, not is_pdf)

    def test_no_safety_option_can_be_replaced_or_appended(self):
        replacements = {
            "--recursive": "--no-recursive",
            "--follow-file-symlinks=2": "--follow-file-symlinks=0",
            "--follow-dir-symlinks=2": "--follow-dir-symlinks=0",
            "--alert-exceeds-max=yes": "--alert-exceeds-max=no",
            "--alert-encrypted=yes": "--alert-encrypted=no",
            "--max-scantime=0": "--max-scantime=900",
            "--no-summary": "--quiet",
            "--": "--exclude=/private",
        }
        for is_pdf in (True, False):
            valid = self.command(is_pdf)
            for original, replacement in replacements.items():
                altered = valid.copy()
                altered[altered.index(original)] = replacement
                with self.subTest(is_pdf=is_pdf, option=original), self.assertRaises(
                    InvalidScannerArguments
                ):
                    self.check(altered, is_pdf)
            size_flags = ("--max-filesize=0", "--max-scansize=0") if is_pdf else (
                "--max-filesize=512M", "--max-scansize=1024M"
            )
            for original in size_flags:
                altered = valid.copy()
                altered[altered.index(original)] = "--max-filesize=2048M"
                with self.subTest(is_pdf=is_pdf, option=original), self.assertRaises(
                    InvalidScannerArguments
                ):
                    self.check(altered, is_pdf)
            for altered in (
                valid + ["--exclude=/private"],
                [valid[0], "--database=/other", *valid[2:]],
                valid[:-1],
            ):
                with self.subTest(is_pdf=is_pdf, argv=altered[-2:]), self.assertRaises(
                    InvalidScannerArguments
                ):
                    self.check(altered, is_pdf)

    def test_fixed_ceilings_and_only_tighter_request_timeouts(self):
        self.assertEqual(gate.MAX_DATABASE_AGE, 48 * 60 * 60)
        self.assertEqual(gate.MAX_FILE_SIZE, 512 * 1024 * 1024)
        self.assertEqual(gate.PDF_SCAN_TIMEOUT, 30 * 60)
        self.assertEqual(gate.CACHE_TTL, 90 * 24 * 60 * 60)
        self.assertEqual(gate.MAX_CONCURRENT_SCANS, 2)
        self.assertEqual(gate.DEFAULT_SCAN_POLICY.pdf_timeout_seconds, 1800)
        self.assertEqual(gate.DEFAULT_SCAN_POLICY.other_timeout_seconds, 180)
        tightened = gate.ScanSecurityPolicySnapshot(pdf_timeout_seconds=60,
                                                     other_timeout_seconds=30)
        self.assertEqual((tightened.pdf_timeout_seconds, tightened.other_timeout_seconds),
                         (60, 30))
        for option in (
            {"pdf_timeout_seconds": 1801}, {"other_timeout_seconds": 181},
            {"pdf_timeout_seconds": 0}, {"other_timeout_seconds": None},
        ):
            with self.subTest(option=option), self.assertRaises(ValueError):
                gate.ScanSecurityPolicySnapshot(**option)
        validate_scanner_version_arguments(
            ["/opt/homebrew/bin/clamscan", "--version"],
            scanner="/opt/homebrew/bin/clamscan",
        )
        with self.assertRaises(InvalidScannerArguments):
            validate_scanner_version_arguments(
                ["/opt/homebrew/bin/clamscan", "--version", "--exclude=/private"],
                scanner="/opt/homebrew/bin/clamscan",
            )

    def test_fixed_inventory_matches_enforcement_and_ci(self):
        document = (ROOT / "docs/scanner/safety-fixed-parameters.md").read_text()
        validator = (ROOT / "scanner_argument_validation.py").read_text()
        scanner = (ROOT / "scan-and-open.py").read_text()
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        for option in (
            *FIXED_FLAGS, "--max-filesize=0", "--max-scansize=0",
            "--max-filesize=512M", "--max-scansize=1024M", "--version",
        ):
            with self.subTest(option=option):
                self.assertIn("`" + option + "`", document)
        self.assertIn("`--database=<installed signatures>`", document)
        self.assertIn("validate_scanner_arguments(command,", scanner)
        self.assertIn("check_database()", scanner)
        self.assertIn("_exact_arguments(command, expected)", validator)
        for test_name in (
            "tests/scanner/fixed-safety-parameters.py",
            "tests/scanner/arguments.py", "tests/scan/policy-snapshot.py",
        ):
            self.assertIn("python3 " + test_name + " -v", workflow)


if __name__ == "__main__":
    unittest.main()
