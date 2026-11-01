#!/usr/bin/env python3
"""Regression contract for the legacy scan/open path after modernization.

Only synthetic files and mocked scanner/native handoffs are used. The real
preference reader, scanner decision, integrity checks, and cache remain active.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import file_launcher

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("legacy_regression_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class LegacyBehaviorRegressions(unittest.TestCase):
    def stub(self, module, name, value=None, **kwargs):
        control = patch.object(module, name, value) if not kwargs else patch.object(module, name, **kwargs)
        mocked = control.start()
        self.addCleanup(control.stop)
        return mocked

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="legacy-behavior-regression-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / "original document.PDF"
        self.original = b"%PDF-1.4\nsynthetic local document\n"
        self.pdf.write_bytes(self.original)
        self.preference = self.root / "target-app.txt"
        self.stub(file_launcher, "TARGET_APP_CONFIG", self.preference)
        self.stub(file_launcher, "FALLBACK_APP_CONFIG", self.root / "fallback-app.txt")
        self.stub(gate, "CACHE_DB", self.root / "clean-cache.sqlite3")
        self.stub(gate, "SCAN_REQUEST_DB", self.root / "requests.sqlite3")
        self.stub(gate, "verify_local_file_available")
        self.stub(gate, "verify_launch_target")
        self.quarantine = self.stub(gate, "remove_quarantine")
        self.launch = self.stub(gate, "launch_clean_file")
        self.stub(gate, "scan_engine_version", return_value="synthetic-clamav")
        self.stub(gate, "read_signature_database_version", return_value="main=1,daily=1")

    def clean_scan(self):
        return subprocess.CompletedProcess([], 0, str(self.pdf) + ": OK\n", "")

    def test_default_brave_scan_and_open_still_requires_a_clean_result(self):
        with patch.object(gate, "run_scan_command", return_value=self.clean_scan()) as scanner:
            result = gate.scan_and_open(self.pdf, "/scanner")
        self.assertEqual(result.status, "clean")
        self.assertFalse(result.from_cache)
        scanner.assert_called_once()
        command = scanner.call_args.args[0]
        self.assertEqual(command[0], "/scanner")
        self.assertEqual(command[-2:], ["--", str(self.pdf)])
        self.assertIn("--alert-encrypted=yes", command)
        self.assertEqual(scanner.call_args.kwargs["timeout"], gate.PDF_SCAN_TIMEOUT)
        self.launch.assert_called_once_with(self.pdf, target_app="com.brave.Browser")
        self.quarantine.assert_called_once_with(self.pdf)
        self.assertEqual(self.pdf.read_bytes(), self.original)
        self.assertFalse(self.preference.exists())

    def test_existing_custom_browser_is_preserved_across_scan_and_cache_handoff(self):
        self.preference.write_text("org.mozilla.firefox\n", encoding="ascii")
        with patch.object(gate, "run_scan_command", return_value=self.clean_scan()) as scanner:
            first = gate.scan_and_open(self.pdf, "/scanner")
            second = gate.scan_and_open(self.pdf, "/scanner")
        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        scanner.assert_called_once()
        self.assertEqual(self.launch.call_count, 2)
        for call in self.launch.call_args_list:
            self.assertEqual(call.args, (self.pdf,))
            self.assertEqual(call.kwargs, {"target_app": "org.mozilla.firefox"})
        self.assertEqual(self.preference.read_text(encoding="ascii"), "org.mozilla.firefox\n")

    def test_malware_incomplete_scan_and_scanner_error_never_open_custom_browser(self):
        self.preference.write_text("org.mozilla.firefox\n", encoding="ascii")
        outcomes = (
            (1, "document: Eicar-Test-Signature FOUND", "", "Malware"),
            (1, "document: Heuristics.Encrypted.PDF FOUND", "", "unscannable"),
            (2, "", "scanner error", "could not finish"),
            (0, "document: OK", "WARNING: skipped object", "did not confirm"),
            (0, "", "", "did not confirm"),
        )
        for index, (returncode, stdout, stderr, message) in enumerate(outcomes):
            with self.subTest(index=index):
                self.pdf.write_bytes(self.original + str(index).encode("ascii"))
                result = subprocess.CompletedProcess([], returncode, stdout, stderr)
                with patch.object(gate, "run_scan_command", return_value=result) as scanner:
                    with self.assertRaisesRegex(RuntimeError, message):
                        gate.scan_and_open(self.pdf, "/scanner")
                scanner.assert_called_once()
                self.launch.assert_not_called()
                self.quarantine.assert_not_called()
        with patch.object(gate, "run_scan_command",
                          side_effect=subprocess.TimeoutExpired("/scanner", 5)) as scanner:
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                gate.scan_and_open(self.pdf, "/scanner")
        scanner.assert_called_once()
        self.launch.assert_not_called()
        self.quarantine.assert_not_called()
        self.assertEqual(self.preference.read_text(encoding="ascii"), "org.mozilla.firefox\n")

    def test_changed_pdf_after_clean_scanner_result_never_reaches_handoff(self):
        self.preference.write_text("org.mozilla.firefox\n", encoding="ascii")

        def modified_during_scan(command, timeout):
            self.pdf.write_bytes(self.original + b"changed after admission")
            return self.clean_scan()

        with patch.object(gate, "run_scan_command", side_effect=modified_during_scan):
            with self.assertRaisesRegex(RuntimeError, "file changed"):
                gate.scan_and_open(self.pdf, "/scanner")
        self.launch.assert_not_called()
        self.quarantine.assert_not_called()
        self.assertEqual(self.preference.read_text(encoding="ascii"), "org.mozilla.firefox\n")

    def test_symlinked_browser_preference_blocks_without_resetting_user_choice(self):
        outside = self.root / "custom-user-setting"
        outside.write_text("org.mozilla.firefox\n", encoding="ascii")
        self.preference.symlink_to(outside)
        with patch.object(gate, "run_scan_command") as scanner:
            with self.assertRaisesRegex(RuntimeError, "Cannot read the PDF application configuration"):
                gate.scan_and_open(self.pdf, "/scanner")
        scanner.assert_not_called()
        self.launch.assert_not_called()
        self.quarantine.assert_not_called()
        self.assertTrue(self.preference.is_symlink())
        self.assertEqual(outside.read_text(encoding="ascii"), "org.mozilla.firefox\n")

    def test_non_pdf_finder_file_retains_system_default_routing(self):
        self.preference.write_text("org.mozilla.firefox\n", encoding="ascii")
        document = self.root / "selected file.txt"
        document.write_bytes(b"synthetic document\n")
        with patch.object(gate, "run_scan_command",
                          return_value=subprocess.CompletedProcess([], 0, str(document) + ": OK", "")) as scanner:
            result = gate.scan_and_open(document, "/scanner")
        self.assertEqual(result.status, "clean")
        self.assertIn("--max-filesize=512M", scanner.call_args.args[0])
        self.assertEqual(scanner.call_args.kwargs["timeout"], gate.OTHER_SCAN_TIMEOUT)
        self.launch.assert_called_once_with(document, target_app=None)
        self.assertEqual(self.preference.read_text(encoding="ascii"), "org.mozilla.firefox\n")

    def test_ci_keeps_independent_legacy_regressions_mandatory(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        for suite in (
            "tests/general/legacy-behavior-regressions.py",
            "tests/general/standard-scanner-parity.py",
            "tests/scan/and-open.py",
            "tests/general/fallback-app.py",
            "tests/scan/file-unavailable-midscan.py",
            "tests/general/brave-pdf-opener.py",
        ):
            with self.subTest(suite=suite):
                self.assertIn("PYTHONPATH=. python3 " + suite, workflow)


if __name__ == "__main__":
    unittest.main()
