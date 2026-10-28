#!/usr/bin/env python3
"""Regression tests for fail-closed scanner failure responses (opener-0255)."""

from dataclasses import FrozenInstanceError
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scan_results import ScanResultStatus
from scanner_failure_policy import (
    INCOMPLETE_MESSAGE,
    INITIALIZATION_MESSAGE,
    PROCESS_MESSAGE,
    SCANNER_FAILURE_RESPONSES,
    TIMEOUT_MESSAGE,
    UNKNOWN_SCANNER_FAILURE_RESPONSE,
    ScannerFailureKind,
    ScannerFailureResponse,
    response_for_scanner_failure,
)

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("failure_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ScannerFailurePolicyTests(unittest.TestCase):
    def test_every_failure_has_terminal_action_and_precise_status(self):
        expected = {
            ScannerFailureKind.INITIALIZATION_FAILED: (
                ScanResultStatus.scanFailed, INITIALIZATION_MESSAGE),
            ScannerFailureKind.PROCESS_FAILED: (
                ScanResultStatus.scanFailed, PROCESS_MESSAGE),
            ScannerFailureKind.INCOMPLETE_RESULT: (
                ScanResultStatus.incompleteScan, INCOMPLETE_MESSAGE),
            ScannerFailureKind.TIMED_OUT: (
                ScanResultStatus.scanTimedOut, TIMEOUT_MESSAGE),
        }
        self.assertEqual(set(SCANNER_FAILURE_RESPONSES), set(ScannerFailureKind))
        for kind, (status, message) in expected.items():
            with self.subTest(kind=kind.value):
                response = response_for_scanner_failure(kind)
                self.assertIs(response, SCANNER_FAILURE_RESPONSES[kind])
                self.assertIs(response.scan_status, status)
                self.assertEqual(response.user_message, message)
                self.assertFalse(response.scan_status.permits_open)
                self.assertTrue(response.show_failure_alert)
                self.assertTrue(response.preserve_quarantine)
                for property_name in (
                    "allow_clean_cache", "allow_open", "allow_fallback",
                    "allow_override", "retry_automatically",
                ):
                    self.assertIs(getattr(response, property_name), False)
                self.assertNotIn("Malware was detected", message)
                self.assertNotIn("/", message)
                self.assertNotIn("\\", message)
                self.assertIn("opening was stopped", message)

    def test_unknown_and_untrusted_failure_kinds_fail_closed(self):
        for value in ("processFailed", "clean", "", None, 0, True, [],
                      {"kind": "processFailed"}, object()):
            with self.subTest(value=repr(value)):
                response = response_for_scanner_failure(value)
                self.assertIs(response, UNKNOWN_SCANNER_FAILURE_RESPONSE)
                self.assertIs(response.scan_status, ScanResultStatus.scanFailed)
                self.assertFalse(response.allow_open)
                self.assertFalse(response.allow_clean_cache)
                self.assertTrue(response.show_failure_alert)
                self.assertNotIn(str(value), response.user_message)

    def test_response_contract_rejects_weakening_and_private_diagnostics(self):
        response = SCANNER_FAILURE_RESPONSES[ScannerFailureKind.PROCESS_FAILED]
        with self.assertRaises(FrozenInstanceError):
            response.allow_open = True
        with self.assertRaises(TypeError):
            SCANNER_FAILURE_RESPONSES[ScannerFailureKind.PROCESS_FAILED] = response
        for options in (
            {"scan_status": ScanResultStatus.clean},
            {"scan_status": "scanFailed"},
            {"user_message": "/private/secret.pdf: scan error"},
            {"user_message": "Malware was detected; opening was stopped."},
            {"show_failure_alert": False},
            {"preserve_quarantine": False},
            {"allow_clean_cache": True},
            {"allow_open": True},
            {"allow_fallback": True},
            {"allow_override": True},
            {"retry_automatically": True},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                ScannerFailureResponse(**({
                    "scan_status": ScanResultStatus.scanFailed,
                    "user_message": PROCESS_MESSAGE,
                } | options))

    def test_real_scan_gate_blocks_scanner_failures_before_caching_or_opening(self):
        with tempfile.TemporaryDirectory(prefix="scanner-failure-policy-") as directory:
            root = Path(directory)
            pdf = root / "fixture.pdf"
            pdf.write_bytes(b"%PDF-1.4\nSynthetic fixture\n")
            outcomes = (
                subprocess.CompletedProcess([], 2, "", "permission denied /private/pdf"),
                subprocess.CompletedProcess([], -9, "", ""),
                subprocess.CompletedProcess([], 1, "", "scanner error"),
                subprocess.CompletedProcess([], 0, "file: OK", "WARNING: skipped"),
                subprocess.CompletedProcess([], 0, "file: Empty file", ""),
            )
            for i, outcome in enumerate(outcomes):
                with self.subTest(exit_code=outcome.returncode, stderr=outcome.stderr):
                    cache = root / ("scan-" + str(i) + ".sqlite3")
                    with patch.object(gate, "CACHE_DB", cache), \
                         patch.object(gate, "intended_destination", return_value="com.brave.Browser"), \
                         patch.object(gate, "pdf_fallback_application", return_value=None), \
                         patch.object(gate, "record_scan_destination"), \
                         patch.object(gate, "verify_launch_target"), \
                         patch.object(gate, "read_signature_database_version", return_value=None), \
                         patch.object(gate, "run_scan_command", return_value=outcome), \
                         patch.object(gate, "remember_clean") as cache_clean, \
                         patch.object(gate, "remove_quarantine") as remove_quarantine, \
                         patch.object(gate, "launch_clean_file") as launch:
                        with self.assertRaises(RuntimeError) as failure:
                            gate.scan_and_open(str(pdf), "/test-scanner")
                    self.assertNotIn(str(pdf), str(failure.exception))
                    self.assertNotIn("Malware was detected", str(failure.exception))
                    cache_clean.assert_not_called()
                    remove_quarantine.assert_not_called()
                    launch.assert_not_called()
                    self.assertEqual(pdf.read_bytes(), b"%PDF-1.4\nSynthetic fixture\n")

    def test_real_gate_blocks_scanner_timeout_and_hides_private_error(self):
        with tempfile.TemporaryDirectory(prefix="scanner-timeout-") as directory:
            root = Path(directory)
            pdf = root / "fixture.pdf"
            pdf.write_bytes(b"%PDF-1.4\nSynthetic fixture\n")
            with patch.object(gate, "CACHE_DB", root / "cache.sqlite"), \
                 patch.object(gate, "intended_destination", return_value="com.brave.Browser"), \
                 patch.object(gate, "pdf_fallback_application", return_value=None), \
                 patch.object(gate, "record_scan_destination"), \
                 patch.object(gate, "verify_launch_target"), \
                 patch.object(gate, "read_signature_database_version", return_value=None), \
                 patch.object(gate, "run_scan_command",
                              side_effect=subprocess.TimeoutExpired(["/private/scanner"], 10)), \
                 patch.object(gate, "remember_clean") as cache_clean, \
                 patch.object(gate, "remove_quarantine") as remove_quarantine, \
                 patch.object(gate, "launch_clean_file") as launch:
                with self.assertRaisesRegex(RuntimeError, "scan timed out") as failure:
                    gate.scan_and_open(str(pdf), "/test-scanner")
            self.assertEqual(str(failure.exception), TIMEOUT_MESSAGE)
            cache_clean.assert_not_called()
            remove_quarantine.assert_not_called()
            launch.assert_not_called()

    def test_process_initialization_failure_is_not_malware_or_clean(self):
        error = OSError("ClamAV failed to start for /private/sensitive.pdf")
        fixed = gate.safe_scan_failure(error)
        self.assertNotIn("/private", fixed)
        self.assertNotIn("Malware was detected", fixed)
        self.assertIn("opening was stopped", fixed)
        self.assertIs(response_for_scanner_failure(
            ScannerFailureKind.INITIALIZATION_FAILED).scan_status,
            ScanResultStatus.scanFailed)

    def test_contract_does_not_add_scanner_processes_or_override_settings(self):
        source = (ROOT / "scanner_failure_policy.py").read_text()
        for forbidden in ("subprocess", "launch_clean_file", "remove_quarantine(",
                          "UserDefaults", "import os", "target-app.txt"):
            self.assertNotIn(forbidden, source)
        gate_source = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("scanner_failure_policy", gate_source)
        self.assertIn("if not decision.allowed:", gate_source)
        self.assertIn("remove_quarantine(path)", gate_source)


if __name__ == "__main__":
    unittest.main()
