#!/usr/bin/env python3
"""opener-0360: validate each ClamAV argument before any scanner execution."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scanner_argument_validation import (
    InvalidScannerArguments,
    validate_scanner_arguments,
    validate_scanner_version_arguments,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("arg_validation_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
UNSET = object()


class ScannerArgumentTests(unittest.TestCase):
    def setUp(self):
        self.scanner = "/opt/homebrew/bin/clamscan"
        self.database = Path("/temporary/clamscan signatures")
        self.document = Path("/temporary/a -flag-looking document.pdf")

    def command(self, *, is_pdf=True):
        limit = ("--max-filesize=0", "--max-scansize=0") if is_pdf else (
            "--max-filesize=512M", "--max-scansize=1024M"
        )
        return [
            self.scanner, "--database=" + str(self.database), "--recursive",
            "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
            "--alert-exceeds-max=yes", "--alert-encrypted=yes", *limit,
            "--max-scantime=0", "--no-summary", "--", str(self.document),
        ]

    def check(self, command, *, is_pdf=True, scanner=UNSET, database=UNSET,
              document=UNSET, timeout=UNSET):
        return validate_scanner_arguments(
            command,
            scanner=self.scanner if scanner is UNSET else scanner,
            database=self.database if database is UNSET else database,
            document=self.document if document is UNSET else document,
            is_pdf=is_pdf,
            timeout=(1800 if is_pdf else 180) if timeout is UNSET else timeout,
        )

    def test_both_fixed_scanner_commands_accept_only_the_intended_modes(self):
        self.check(self.command())
        self.check(self.command(), timeout=1)
        self.check(self.command(is_pdf=False), is_pdf=False)
        self.check(self.command(is_pdf=False), is_pdf=False, timeout=1)
        with self.assertRaises(InvalidScannerArguments):
            self.check(self.command(is_pdf=False))
        with self.assertRaises(InvalidScannerArguments):
            self.check(self.command(), is_pdf=False)

    def test_every_command_argument_is_independently_verified(self):
        valid = self.command()
        for index in range(len(valid)):
            with self.subTest(argument=index):
                changed = valid.copy()
                changed[index] = "unapproved-argument"
                with self.assertRaisesRegex(InvalidScannerArguments,
                                            "^Invalid scanner arguments; opening was stopped"):
                    self.check(changed)
        for invalid in (
            valid[:-1], valid + ["--exclude=/tmp"], valid[:2] + valid[3:],
            valid[:], tuple(valid) + ("--quiet",),
            [*valid[:5], None, *valid[6:]], " ".join(valid), None, {},
        ):
            with self.subTest(command=repr(invalid)[:80]):
                if invalid is not valid and invalid != valid:
                    with self.assertRaises(InvalidScannerArguments):
                        self.check(invalid)
        changed = valid.copy()
        changed[1], changed[2] = changed[2], changed[1]
        with self.assertRaises(InvalidScannerArguments):
            self.check(changed)

    def test_nonpdf_limits_cannot_be_silently_relaxed(self):
        valid = self.command(is_pdf=False)
        for index, value in ((7, "--max-filesize=0"), (8, "--max-scansize=0"),
                             (5, "--alert-exceeds-max=no"),
                             (6, "--alert-encrypted=no"), (9, "--max-scantime=60"),
                             (11, "/temporary/input.pdf")):
            changed = valid.copy()
            changed[index] = value
            with self.subTest(argument=index), self.assertRaises(InvalidScannerArguments):
                self.check(changed, is_pdf=False)

    def test_executable_database_document_and_timeout_inputs_are_checked(self):
        valid = self.command()
        for bad in ("clamscan", "--help", "", "/tmp/clamscan\n--help",
                    "/tmp/clamscan\0bad", 1, None):
            with self.subTest(scanner=repr(bad)), self.assertRaises(InvalidScannerArguments):
                self.check(valid, scanner=bad)
        for bad in ("relative/database", Path("relative/database"),
                    Path("/tmp/db\n--exclude"), Path("/tmp/db\0x"), None):
            with self.subTest(database=repr(bad)), self.assertRaises(InvalidScannerArguments):
                self.check(valid, database=bad)
        for bad in (Path("relative.pdf"), Path("/tmp/bad\0.pdf"), "path.pdf", None):
            with self.subTest(document=repr(bad)), self.assertRaises(InvalidScannerArguments):
                self.check(valid, document=bad)
        for invalid in (0, -1, 1801, True, 1.5, "30"):
            with self.subTest(timeout=invalid), self.assertRaises(InvalidScannerArguments):
                self.check(valid, timeout=invalid)
        with self.assertRaises(InvalidScannerArguments):
            validate_scanner_arguments(valid, scanner=self.scanner,
                database=self.database, document=self.document, is_pdf="pdf", timeout=1800)

    def test_document_path_with_spaces_newlines_and_option_text_remains_one_operand(self):
        path = Path("/temporary/-strange\n--alert-encrypted=no document.pdf")
        command = self.command()
        command[-1] = str(path)
        self.check(command, document=path)
        self.assertEqual(command[-2], "--")
        self.assertEqual(command[-1], str(path))

    def test_version_probe_accepts_only_one_fixed_option(self):
        good = [self.scanner, "--version"]
        validate_scanner_version_arguments(good, scanner=self.scanner)
        for bad in (
            [self.scanner, "--help"], [self.scanner, "--version", "--exclude=."],
            ["clamscan", "--version"], [self.scanner], None,
        ):
            with self.subTest(command=bad), self.assertRaises(InvalidScannerArguments):
                validate_scanner_version_arguments(bad, scanner=self.scanner)
        with patch.object(gate.subprocess, "check_output") as version:
            self.assertIsNone(gate.scan_engine_version("/bad\n--help"))
            version.assert_not_called()

    def test_invalid_executable_blocks_real_scan_gate_before_spawn_or_launch(self):
        with tempfile.TemporaryDirectory(prefix="scanner-argument-gate-") as directory:
            path = Path(directory) / "untrusted.pdf"
            path.write_bytes(b"%PDF-1.4\nsynthetic test fixture")
            with patch.object(gate, "CACHE_DB", Path(directory) / "cache.sqlite3"), \
                 patch.object(gate, "SCAN_REQUEST_DB", Path(directory) / "requests.sqlite3"), \
                 patch.object(gate, "record_scan_destination"), \
                 patch.object(gate, "intended_destination", return_value="com.brave.Browser"), \
                 patch.object(gate, "pdf_fallback_application", return_value=None), \
                 patch.object(gate, "verify_local_file_available"), \
                 patch.object(gate, "run_scan_command") as run, \
                 patch.object(gate, "remove_quarantine") as quarantine, \
                 patch.object(gate, "launch_clean_file") as launch:
                for invalid in ("clamscan", "/tmp/clamscan\0bad", "/tmp/clamscan\n--help"):
                    with self.subTest(scanner=repr(invalid)):
                        with self.assertRaises(InvalidScannerArguments):
                            gate.scan_and_open(path, invalid)
                run.assert_not_called()
                quarantine.assert_not_called()
                launch.assert_not_called()
                self.assertFalse((Path(directory) / "cache.sqlite3").exists())

    def test_invalid_database_option_blocks_real_scan_before_execution(self):
        with tempfile.TemporaryDirectory(prefix="scanner-database-gate-") as directory:
            path = Path(directory) / "untrusted.pdf"
            path.write_bytes(b"%PDF-1.4\nsynthetic test fixture")
            with patch.object(gate, "CACHE_DB", Path(directory) / "cache.sqlite3"), \
                 patch.object(gate, "SCAN_REQUEST_DB", Path(directory) / "requests.sqlite3"), \
                 patch.object(gate, "DATABASE", Path(directory) / "signatures\n--quiet"), \
                 patch.object(gate, "record_scan_destination"), \
                 patch.object(gate, "intended_destination", return_value="com.brave.Browser"), \
                 patch.object(gate, "pdf_fallback_application", return_value=None), \
                 patch.object(gate, "verify_local_file_available"), \
                 patch.object(gate, "run_scan_command") as run, \
                 patch.object(gate, "launch_clean_file") as launch:
                with self.assertRaises(InvalidScannerArguments):
                    gate.scan_and_open(path, self.scanner)
                run.assert_not_called()
                launch.assert_not_called()

    def test_valid_real_gate_passes_exact_arguments_and_keeps_clean_policy(self):
        with tempfile.TemporaryDirectory(prefix="scanner-argument-allowed-") as directory:
            path = Path(directory) / "--report.pdf"
            path.write_bytes(b"%PDF-1.4\nsynthetic test fixture")
            clean = subprocess.CompletedProcess([], 0, "report: OK\n", "")
            with patch.object(gate, "CACHE_DB", Path(directory) / "cache.sqlite3"), \
                 patch.object(gate, "SCAN_REQUEST_DB", Path(directory) / "requests.sqlite3"), \
                 patch.object(gate, "record_scan_destination"), \
                 patch.object(gate, "intended_destination", return_value="com.brave.Browser"), \
                 patch.object(gate, "pdf_fallback_application", return_value=None), \
                 patch.object(gate, "verify_local_file_available"), \
                 patch.object(gate, "read_signature_database_version", return_value="main=1,daily=2"), \
                 patch.object(gate, "verify_launch_target"), \
                 patch.object(gate, "scan_engine_version", return_value="test"), \
                 patch.object(gate, "run_scan_command", return_value=clean) as run, \
                 patch.object(gate, "launch_clean_file") as launch:
                result = gate.scan_and_open(path, self.scanner)
                self.assertEqual(result.status, "clean")
                run.assert_called_once()
                command = run.call_args.args[0]
                validate_scanner_arguments(command, scanner=self.scanner,
                    database=gate.DATABASE, document=path, is_pdf=True,
                    timeout=gate.PDF_SCAN_TIMEOUT)
                launch.assert_called_once()

    def test_ci_runs_validation_regression(self):
        source = (ROOT / "scan-and-open.py").read_text()
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("validate_scanner_arguments(command,", source)
        self.assertIn("validate_scanner_version_arguments(version_command,", source)
        self.assertIn("python3 tests/scanner/arguments.py -v", workflow)


if __name__ == "__main__":
    unittest.main()
