#!/usr/bin/env python3
"""opener-0348: record a fixed rejection reason, never an approved exemption."""

from dataclasses import FrozenInstanceError, replace
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from protection_exception_policy import (
    EXCEPTION_REJECTION_REASON,
    EXCEPTION_SUPPORT_DECISION,
    ExceptionDisposition,
    ExceptionRejectionCode,
    ExceptionRejectionReason,
    ProtectionExceptionNotSupported,
    UNSUPPORTED_EXCEPTION_MESSAGE,
    record_exception_rejection_reason,
    request_protection_exception,
)

ROOT = Path(__file__).resolve().parents[2]


class ExceptionReasonTests(unittest.TestCase):
    def test_the_only_recorded_reason_is_a_fixed_policy_denial(self):
        record = EXCEPTION_REJECTION_REASON
        self.assertIs(record, record_exception_rejection_reason())
        self.assertIs(record, EXCEPTION_SUPPORT_DECISION.rejection_reason)
        self.assertIs(record.code, ExceptionRejectionCode.MANDATORY_PROTECTION_NO_EXCEPTIONS)
        self.assertIs(record.disposition, ExceptionDisposition.UNSUPPORTED)
        self.assertEqual(record.explanation, UNSUPPORTED_EXCEPTION_MESSAGE)
        self.assertFalse(EXCEPTION_SUPPORT_DECISION.supported)
        self.assertEqual(record.as_document(), {
            "reason_code": "mandatory_protection_no_exceptions",
            "reason": UNSUPPORTED_EXCEPTION_MESSAGE,
            "disposition": "unsupported",
            "exception_granted": False,
        })

    def test_rejected_exception_exposes_reason_without_approval(self):
        with self.assertRaises(ProtectionExceptionNotSupported) as raised:
            request_protection_exception({"approved": True, "reason": "let this open"})
        error = raised.exception
        self.assertIs(error.reason_record, EXCEPTION_REJECTION_REASON)
        self.assertEqual(str(error), UNSUPPORTED_EXCEPTION_MESSAGE)
        self.assertFalse(error.reason_record.as_document()["exception_granted"])

    def test_hostile_sensitive_payload_is_never_inspected_or_retained(self):
        class HostileRequest:
            def __getattribute__(self, name):
                raise AssertionError("Never inspect a proposed exception")
            def __repr__(self):
                raise AssertionError("Never render proposed exception")
            def __str__(self):
                raise AssertionError("Never log proposed exception")
        requests = (
            HostileRequest(),
            {"path": "/private/secrets.pdf", "reason": "confidential note"},
            "/Users/private/paper.pdf",
        )
        for attempt in requests:
            with self.subTest(type=type(attempt).__name__):
                record = record_exception_rejection_reason(attempt)
                self.assertIs(record, EXCEPTION_REJECTION_REASON)
                with self.assertRaises(ProtectionExceptionNotSupported) as caught:
                    request_protection_exception(attempt)
                self.assertIs(caught.exception.reason_record, record)
                self.assertNotIn("/private/", str(record.as_document()))
                self.assertNotIn("confidential note", str(record.as_document()))

    def test_reason_record_is_immutable_and_rejects_forged_approvals(self):
        record = EXCEPTION_REJECTION_REASON
        with self.assertRaises(FrozenInstanceError):
            record.explanation = "allowed"
        with self.assertRaises(FrozenInstanceError):
            record.code = ExceptionRejectionCode.MANDATORY_PROTECTION_NO_EXCEPTIONS
        invalid = (
            {"code": "approved"},
            {"code": None},
            {"explanation": "User exception approved"},
            {"explanation": None},
            {"disposition": "approved"},
            {"disposition": None},
        )
        for mutation in invalid:
            with self.subTest(mutation=mutation), self.assertRaises(
                ProtectionExceptionNotSupported
            ):
                replace(record, **mutation)
        copied = record.as_document()
        copied["exception_granted"] = True
        copied["reason"] = "approved"
        self.assertFalse(record.as_document()["exception_granted"])
        self.assertEqual(record.explanation, UNSUPPORTED_EXCEPTION_MESSAGE)

    def test_reason_not_a_scanner_policy_preference_or_exception_registry(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        view = (ROOT / "PDFMagicOpenerApp/ProtectionSettingsView.swift").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "record_exception_rejection_reason",
            "EXCEPTION_REJECTION_REASON",
            "exception_granted",
            "exception_allowlist",
        ):
            self.assertNotIn(forbidden, scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIn("decision = decide_opening(detection)", scanner)
        self.assertIn('GroupBox("Protection exceptions")', view)
        self.assertIn("Protection exceptions are not supported.", view)

    def test_detected_malware_is_still_blocked_despite_recorded_denial_reason(self):
        spec = importlib.util.spec_from_file_location(
            "exception_reason_scanner_test", ROOT / "scan-and-open.py"
        )
        scanner = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(scanner)
        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / "untrusted.pdf"
            selected.write_bytes(b"%PDF-1.4\nuntrusted")
            result = subprocess.CompletedProcess(
                [], 1, f"{selected}: Test.Malware FOUND\n", ""
            )
            with patch.object(scanner, "CACHE_DB", Path(tmp) / "cache.sqlite3"), \
                 patch.object(scanner, "SCAN_REQUEST_DB", Path(tmp) / "requests.sqlite3"), \
                 patch.object(scanner, "verify_launch_target"), \
                 patch.object(scanner.subprocess, "check_output", side_effect=FileNotFoundError), \
                 patch.object(scanner.subprocess, "run", return_value=result) as run, \
                 patch.object(scanner, "remember_clean") as cache, \
                 patch.object(scanner, "launch_clean_file") as opened:
                self.assertIsNotNone(
                    record_exception_rejection_reason({"path": str(selected)})
                )
                with self.assertRaises(RuntimeError):
                    scanner.scan_and_open(
                        str(selected), "/scanner", protection_level="exempt"
                    )
                run.assert_called_once()
                cache.assert_not_called()
                opened.assert_not_called()


if __name__ == "__main__":
    unittest.main()
