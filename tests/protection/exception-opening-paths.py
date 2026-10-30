#!/usr/bin/env python3
"""opener-0353: rejected exceptions must not create an unintended opening path."""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from protection_exception_policy import (
    EXCEPTION_SUPPORT_DECISION,
    ProtectionExceptionNotSupported,
    record_exception_rejection_reason,
    request_protection_exception,
)
from protection_failure_exception_boundary import report_protection_block
from scanner_failure_policy import ScannerFailureKind

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "opener353_gate", (Path(__file__).resolve().parents[2]s[2] / "scan-and-open.py")
)
gate = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(gate)


class ExceptionOpeningPathTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="opener353-")
        self.addCleanup(temp.cleanup)
        self.pdf = Path(temp.name) / "untrusted.pdf"
        self.original = b"%PDF-1.4\nSynthetic untrusted test PDF\n"
        self.pdf.write_bytes(self.original)
        self.enterContext(patch.object(gate, "CACHE_DB", Path(temp.name) / "cache.sqlite3"))
        self.enterContext(patch.object(gate, "SCAN_REQUEST_DB", Path(temp.name) / "requests.sqlite3"))
        self.enterContext(patch.object(gate, "intended_destination", return_value="selected-viewer"))
        self.enterContext(patch.object(gate, "pdf_fallback_application", return_value="other-viewer"))
        self.enterContext(patch.object(gate, "scan_engine_version", return_value="synthetic-v1"))
        self.enterContext(patch.object(gate, "read_signature_database_version", return_value="main=42"))
        for name in ("verify_local_file_available", "verify_launch_target", "record_scan_destination"):
            self.enterContext(patch.object(gate, name))
        self.scan = self.enterContext(patch.object(gate, "run_scan_command"))
        self.opened = self.enterContext(patch.object(gate, "launch_clean_file"))
        self.quarantine = self.enterContext(patch.object(gate, "remove_quarantine"))
        self.cache_write = self.enterContext(patch.object(gate, "remember_clean", wraps=gate.remember_clean))
        self.origin = self.enterContext(patch.object(gate, "record_opened_document_origin"))

    def requested_open(self):
        # Claimed exceptions are descriptive metadata, never trusted verdicts.
        return gate.scan_and_open(
            str(self.pdf), "/synthetic-scanner",
            protection_level="exception-approved-skip-checks",
            source_url="https://example.invalid/report.pdf?approved=true",
        )

    def assert_blocked_side_effects(self):
        self.opened.assert_not_called()
        self.quarantine.assert_not_called()
        self.cache_write.assert_not_called()
        self.origin.assert_not_called()

    def test_rejected_requests_and_reports_never_authorize_open(self):
        class PoisonRequest:
            def __getattribute__(self, name):
                raise AssertionError("Exception request must not be inspected")
            def __str__(self):
                raise AssertionError("Exception request must not be logged")

        self.assertFalse(EXCEPTION_SUPPORT_DECISION.supported)
        for payload in (
            {"approved": True, "skip_scan": True},
            {"file": str(self.pdf), "trusted_source": True},
            PoisonRequest(),
        ):
            with self.subTest(payload_type=type(payload).__name__):
                with self.assertRaises(ProtectionExceptionNotSupported):
                    request_protection_exception(payload)
                reason = record_exception_rejection_reason(payload)
                self.assertFalse(reason.as_document()["exception_granted"])
                report = report_protection_block(feature_exception_request=payload)
                self.assertFalse(report.authorizes_open)
                self.assertFalse(report.user_exception_approved)
                self.assertFalse(report.to_dict()["authorizesOpen"])
        self.scan.assert_not_called()
        self.assert_blocked_side_effects()

    def test_exception_labels_never_open_blocked_or_inconclusive_scans(self):
        outcomes = (
            ("malware", 1, "untrusted.pdf: Test.Malware FOUND\n", ""),
            ("heuristic", 1, "untrusted.pdf: Heuristics.Encrypted.PDF FOUND\n", ""),
            ("scanner_error", 2, "", "scanner error"),
            ("missing_ok", 0, "", ""),
            ("stderr", 0, "untrusted.pdf: OK\n", "partial scan warning"),
            ("skipped", 0, "untrusted.pdf: OK\nSKIPPED\n", ""),
        )
        for name, code, stdout, stderr in outcomes:
            with self.subTest(outcome=name):
                for mock in (self.scan, self.opened, self.quarantine, self.cache_write, self.origin):
                    mock.reset_mock()
                self.scan.return_value = subprocess.CompletedProcess([], code, stdout, stderr)
                with self.assertRaises(RuntimeError):
                    self.requested_open()
                self.scan.assert_called_once()
                self.assert_blocked_side_effects()
                self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_failed_scan_cannot_be_reused_as_exception_cache_hit(self):
        self.scan.return_value = subprocess.CompletedProcess(
            [], 1, "untrusted.pdf: Test.Malware FOUND\n", ""
        )
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "Malware"):
                self.requested_open()
        self.assertEqual(self.scan.call_count, 2)
        self.assert_blocked_side_effects()

    def test_unknown_exception_bypass_keywords_fail_before_scanning(self):
        for keyword in ("skip_scan", "allowlisted", "exception_approved", "open_anyway"):
            with self.subTest(keyword=keyword):
                with self.assertRaises(TypeError):
                    gate.scan_and_open(str(self.pdf), "/synthetic-scanner", **{keyword: True})
        self.scan.assert_not_called()
        self.assert_blocked_side_effects()

    def test_changed_file_cannot_be_opened_with_exception_label(self):
        def modify(_command, timeout):
            self.pdf.write_bytes(self.original + b"changed during scan\n")
            return subprocess.CompletedProcess([], 0, "untrusted.pdf: OK\n", "")
        self.scan.side_effect = modify
        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.requested_open()
        self.scan.assert_called_once()
        self.assert_blocked_side_effects()

    def test_real_clean_scan_required_even_when_exception_is_claimed(self):
        self.scan.return_value = subprocess.CompletedProcess([], 0, "untrusted.pdf: OK\n", "")
        result = self.requested_open()
        self.assertEqual(result.status, "clean")
        self.assertEqual(result.effective_policy_id, "built-in")
        self.assertFalse(result.from_cache)
        self.scan.assert_called_once()
        self.cache_write.assert_called_once()
        self.opened.assert_called_once_with(self.pdf.resolve(), target_app="selected-viewer")
        self.origin.assert_called_once_with("original")

    def test_scanner_failure_report_takes_precedence_over_exception(self):
        report = report_protection_block(
            ScannerFailureKind.PROCESS_FAILED,
            feature_exception_request={"approved": True, "open_anyway": True},
        )
        self.assertEqual(report.origin.value, "scannerFailure")
        self.assertFalse(report.authorizes_open)
        self.assertFalse(report.scan_status.permits_open)
        self.scan.assert_not_called()
        self.assert_blocked_side_effects()


if __name__ == "__main__":
    unittest.main()
