#!/usr/bin/env python3
"""Regression coverage for PRs #21 and #235 on the current scanner gate."""

from contextlib import redirect_stderr
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "scanner_executable_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ScannerExecutableAccessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.scanner = self.root / "clamscan"
        self.scanner.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.scanner.chmod(0o700)
        self.directory = self.root / "scanner-directory"
        self.directory.mkdir()
        self.pdf = self.root / "document.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")

    def candidates(self, *paths):
        return patch.object(gate, "CLAMAV_CANDIDATES", tuple(map(str, paths)))

    def test_regular_executable_is_selected_without_scanning(self):
        with self.candidates(self.scanner), \
                patch.object(gate, "require_supported_scanner_version", return_value="1.5.0") as version, \
                patch.object(gate, "run_scan_command") as run:
            self.assertEqual(gate.scanner_path(), str(self.scanner))
        version.assert_called_once_with(str(self.scanner))
        run.assert_not_called()

    def test_executable_symlink_remains_supported(self):
        alias = self.root / "clamscan-link"
        alias.symlink_to(self.scanner)
        with self.candidates(alias), \
                patch.object(gate, "require_supported_scanner_version", return_value="1.5.0"):
            self.assertEqual(gate.scanner_path(), str(alias))

    def test_missing_dangling_and_nonexecutable_files_are_rejected(self):
        missing = self.root / "missing"
        broken = self.root / "broken-link"
        broken.symlink_to(missing)
        disabled = self.root / "disabled-clamscan"
        disabled.write_bytes(b"not executable")
        disabled.chmod(0o600)
        for candidate in (missing, broken, disabled):
            with self.subTest(candidate=candidate.name), self.candidates(candidate), \
                    patch.object(gate, "require_supported_scanner_version") as version:
                with self.assertRaisesRegex(RuntimeError, "^ClamAV is unavailable"):
                    gate.scanner_path()
                version.assert_not_called()

    def test_searchable_directory_cannot_be_selected_as_scanner(self):
        self.assertTrue(os.access(self.directory, os.X_OK))
        with self.candidates(self.directory), \
                patch.object(gate, "require_supported_scanner_version") as version:
            with self.assertRaisesRegex(RuntimeError, "^ClamAV is unavailable"):
                gate.scanner_path()
            version.assert_not_called()

    def test_invalid_first_candidate_falls_back_to_valid_executable(self):
        with self.candidates(self.directory, self.scanner), \
                patch.object(gate, "require_supported_scanner_version", return_value="1.5.0"):
            self.assertEqual(gate.scanner_path(), str(self.scanner))

    def test_invalid_scanner_fails_before_signatures_scan_cache_and_open(self):
        diagnostics = io.StringIO()
        with self.candidates(self.directory), \
                patch.object(gate, "watch_parent_lifetime"), \
                patch.object(gate, "require_supported_scanner_version") as version, \
                patch.object(gate, "check_database") as signatures, \
                patch.object(gate, "scan_and_open") as scan, \
                patch.object(gate, "cached_scan") as cache, \
                patch.object(gate, "remove_quarantine") as quarantine, \
                patch.object(gate, "launch_clean_file") as launch, \
                redirect_stderr(diagnostics):
            self.assertEqual(gate.main([str(self.pdf)]), 1)
        for action in (version, signatures, scan, cache, quarantine, launch):
            action.assert_not_called()
        self.assertIn("ClamAV is unavailable", diagnostics.getvalue())
        self.assertNotIn(str(self.pdf), diagnostics.getvalue())
        self.assertEqual(self.pdf.read_bytes(), b"%PDF-1.4\n")

    def test_both_original_regressions_are_registered_in_correct_ci_jobs(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        scanners, macos = ci.split("  macos-build:", maxsplit=1)
        self.assertIn("  scanner-tests:", scanners)
        self.assertIn("python3 scripts/run-test.py tests/scanner/executable-access.py -v", scanners)
        self.assertIn("python3 scripts/run-test.py tests/general/brave-pdf-opener.py", macos)


if __name__ == "__main__":
    unittest.main()
