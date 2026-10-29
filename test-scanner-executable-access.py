#!/usr/bin/env python3
"""opener-0356: only a runnable regular file can be selected as ClamAV."""

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
spec = importlib.util.spec_from_file_location("scanner_executable_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ScannerExecutableAccessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.executable = self.root / "clamscan"
        self.executable.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.executable.chmod(0o700)
        self.directory = self.root / "scanner-directory"
        self.directory.mkdir()
        self.pdf = self.root / "document.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\n")

    def test_accessible_regular_executable_is_selected_without_running_it(self):
        with patch.object(gate, "SCANNER_CANDIDATES", (str(self.executable),)), \
                patch.object(gate, "run_scan_command") as run:
            self.assertEqual(gate.scanner_path(), str(self.executable))
            run.assert_not_called()

    def test_valid_executable_symlink_is_supported(self):
        alias = self.root / "clamscan-link"
        alias.symlink_to(self.executable)
        with patch.object(gate, "SCANNER_CANDIDATES", (str(alias),)):
            self.assertEqual(gate.scanner_path(), str(alias))

    def test_missing_broken_link_and_unexecutable_file_are_rejected(self):
        missing = self.root / "missing"
        broken = self.root / "broken-link"
        broken.symlink_to(missing)
        disabled = self.root / "disabled-clamscan"
        disabled.write_bytes(b"not executable")
        disabled.chmod(0o600)
        for candidate in (missing, broken, disabled):
            with self.subTest(candidate=candidate.name), \
                    patch.object(gate, "SCANNER_CANDIDATES", (str(candidate),)):
                with self.assertRaisesRegex(RuntimeError, "ClamAV is unavailable"):
                    gate.scanner_path()

    def test_searchable_directory_is_not_mistaken_for_an_executable(self):
        self.assertTrue(os.access(self.directory, os.X_OK))
        with patch.object(gate, "SCANNER_CANDIDATES", (str(self.directory),)):
            with self.assertRaisesRegex(RuntimeError, "ClamAV is unavailable"):
                gate.scanner_path()

    def test_inaccessible_candidate_falls_back_to_existing_valid_install(self):
        with patch.object(gate, "SCANNER_CANDIDATES",
                          (str(self.directory), str(self.executable))):
            self.assertEqual(gate.scanner_path(), str(self.executable))

    def test_invalid_executable_blocks_before_signature_checks_and_opening(self):
        diagnostics = io.StringIO()
        with patch.object(gate, "SCANNER_CANDIDATES", (str(self.directory),)), \
                patch.object(gate, "check_database") as signatures, \
                patch.object(gate, "scan_and_open") as scan, \
                patch.object(gate, "remove_quarantine") as quarantine, \
                patch.object(gate, "launch_clean_file") as launch, \
                redirect_stderr(diagnostics):
            self.assertEqual(gate.main([str(self.pdf)]), 1)
            signatures.assert_not_called()
            scan.assert_not_called()
            quarantine.assert_not_called()
            launch.assert_not_called()
        self.assertIn("ClamAV is unavailable", diagnostics.getvalue())
        self.assertNotIn(str(self.pdf), diagnostics.getvalue())
        self.assertEqual(self.pdf.read_bytes(), b"%PDF-1.4\n")

    def test_regression_is_registered_in_ci(self):
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-scanner-executable-access.py -v", ci)


if __name__ == "__main__":
    unittest.main()
