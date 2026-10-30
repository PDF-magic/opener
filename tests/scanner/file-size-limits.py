#!/usr/bin/env python3
"""opener-0399: validate permitted scanner file-size limits without enabling overrides."""

import unittest
from pathlib import Path

from scanner_argument_validation import (
    InvalidScannerArguments,
    validate_scanner_arguments,
    validated_file_size_options,
)


class ScannerFileSizeLimitTests(unittest.TestCase):
    def test_existing_default_flags_are_unchanged(self):
        self.assertEqual(
            validated_file_size_options(is_pdf=True),
            ("--max-filesize=0", "--max-scansize=0"),
        )
        self.assertEqual(
            validated_file_size_options(is_pdf=False),
            ("--max-filesize=512M", "--max-scansize=1024M"),
        )
        self.assertEqual(
            validated_file_size_options(is_pdf=True, file_limit_mib=0, scan_limit_mib=0),
            validated_file_size_options(is_pdf=True),
        )
        self.assertEqual(
            validated_file_size_options(
                is_pdf=False, file_limit_mib=512, scan_limit_mib=1024
            ),
            validated_file_size_options(is_pdf=False),
        )

    def test_tighter_non_pdf_proposals_must_stay_within_both_caps(self):
        for file_limit, scan_limit in ((1, 1), (64, 128), (512, 512), (512, 1024)):
            with self.subTest(file=file_limit, aggregate=scan_limit):
                self.assertEqual(
                    validated_file_size_options(
                        is_pdf=False,
                        file_limit_mib=file_limit,
                        scan_limit_mib=scan_limit,
                    ),
                    (f"--max-filesize={file_limit}M", f"--max-scansize={scan_limit}M"),
                )

    def test_non_pdf_limits_cannot_be_disabled_or_relaxed(self):
        invalid = (
            (0, 1024), (512, 0), (0, 0), (-1, 1024), (512, -1),
            (513, 1024), (512, 1025), (512, 511), (2**64, 2**64),
            (True, 1024), (512, False), (1.5, 1024), (512, 1024.0),
            ("512", 1024), (512, "1024"), ([], 1024), (512, {}),
        )
        for file_limit, scan_limit in invalid:
            with self.subTest(file=repr(file_limit), aggregate=repr(scan_limit)):
                with self.assertRaises(InvalidScannerArguments):
                    validated_file_size_options(
                        is_pdf=False,
                        file_limit_mib=file_limit,
                        scan_limit_mib=scan_limit,
                    )

    def test_pdf_limits_are_only_the_existing_unlimited_pair(self):
        for file_limit, scan_limit in (
            (1, 0), (0, 1), (512, 1024), (-1, 0),
            (True, 0), (0, False), (0.0, 0), (0, "0"),
        ):
            with self.subTest(file=repr(file_limit), aggregate=repr(scan_limit)):
                with self.assertRaises(InvalidScannerArguments):
                    validated_file_size_options(
                        is_pdf=True,
                        file_limit_mib=file_limit,
                        scan_limit_mib=scan_limit,
                    )

    def test_mode_type_must_be_real_boolean(self):
        for mode in (1, 0, None, "pdf", [], {}):
            with self.subTest(mode=repr(mode)):
                with self.assertRaises(InvalidScannerArguments):
                    validated_file_size_options(is_pdf=mode)

    def test_active_argv_remains_fixed_even_for_tighter_valid_proposals(self):
        scanner = "/opt/homebrew/bin/clamscan"
        database = Path("/tmp/synthetic-signatures")
        document = Path("/tmp/synthetic-report.txt")
        command = [
            scanner, "--database=" + str(database), "--recursive",
            "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
            "--alert-exceeds-max=yes", "--alert-encrypted=yes",
            *validated_file_size_options(is_pdf=False),
            "--max-scantime=0", "--no-summary", "--", str(document),
        ]
        validate_scanner_arguments(
            command, scanner=scanner, database=database,
            document=document, is_pdf=False, timeout=180,
        )
        changed = command.copy()
        changed[7:9] = validated_file_size_options(
            is_pdf=False, file_limit_mib=256, scan_limit_mib=512
        )
        with self.assertRaises(InvalidScannerArguments):
            validate_scanner_arguments(
                changed, scanner=scanner, database=database,
                document=document, is_pdf=False, timeout=180,
            )
        pdf = command.copy()
        pdf[7:9] = validated_file_size_options(is_pdf=True)
        validate_scanner_arguments(
            pdf, scanner=scanner, database=database,
            document=document, is_pdf=True, timeout=1800,
        )
        with self.assertRaises(InvalidScannerArguments):
            validate_scanner_arguments(
                pdf, scanner=scanner, database=database,
                document=document, is_pdf=False, timeout=180,
            )

    def test_runtime_gate_and_ci_use_validator(self):
        root = Path(__file__).resolve().parent
        source = (root / "scan-and-open.py").read_text()
        validator = (root / "scanner_argument_validation.py").read_text()
        workflow = (root / ".github/workflows/ci.yml").read_text()
        self.assertIn("size_options = validated_file_size_options(is_pdf=is_pdf)", source)
        self.assertIn("size_options = validated_file_size_options(is_pdf=is_pdf)", validator)
        self.assertIn("python3 scripts/run-test.py tests/scanner/file-size-limits.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
