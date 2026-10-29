#!/usr/bin/env python3
"""opener-0344: feature exception requests never mask scanner failures."""

from dataclasses import FrozenInstanceError, replace
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scan_results import ScanResultStatus
from scanner_failure_policy import ScannerFailureKind, response_for_scanner_failure
from protection_exception_policy import (
    EXCEPTION_SUPPORT_DECISION,
    ProtectionExceptionNotSupported,
    UNSUPPORTED_EXCEPTION_MESSAGE,
    request_protection_exception,
)
from protection_failure_exception_boundary import (
    EXCEPTION_REJECTION_MESSAGE,
    ProtectionBlockOrigin,
    ProtectionBlockReport,
    report_protection_block,
)

ROOT = Path(__file__).resolve().parent


class ProtectionFailureExceptionBoundaryTests(unittest.TestCase):
    def test_all_known_failures_keep_specific_terminal_status_and_message(self):
        for kind in ScannerFailureKind:
            with self.subTest(kind=kind):
                authoritative = response_for_scanner_failure(kind)
                baseline = report_protection_block(kind)
                with_claim = report_protection_block(
                    kind, feature_exception_request={"approved": True,
                                                     "feature": "interactive form"},
                )
                self.assertEqual(with_claim, baseline)
                self.assertIs(with_claim.origin, ProtectionBlockOrigin.SCANNER_FAILURE)
                self.assertIs(with_claim.scan_status, authoritative.scan_status)
                self.assertEqual(with_claim.message, authoritative.user_message)
                self.assertFalse(with_claim.authorizes_open)
                self.assertFalse(with_claim.user_exception_approved)
                self.assertFalse(with_claim.scan_status.permits_open)
                self.assertEqual(with_claim.to_dict(), {
                    "origin": "scannerFailure",
                    "scanStatus": authoritative.scan_status.value,
                    "message": authoritative.user_message,
                    "authorizesOpen": False,
                    "userExceptionApproved": False,
                })

    def test_exception_rejection_matches_authoritative_unsupported_policy(self):
        self.assertIs(EXCEPTION_REJECTION_MESSAGE, UNSUPPORTED_EXCEPTION_MESSAGE)
        self.assertFalse(EXCEPTION_SUPPORT_DECISION.supported)
        with self.assertRaises(ProtectionExceptionNotSupported) as raised:
            request_protection_exception({"approved": True, "feature": "interactive form"})
        self.assertEqual(str(raised.exception), EXCEPTION_REJECTION_MESSAGE)

    def test_exception_requests_rejected_without_forging_scanner_outcome(self):
        class Poison:
            def __getattribute__(self, key):
                raise AssertionError("Do not inspect a user exception request")
            def __str__(self):
                raise AssertionError("Do not log request content")

        for request in ("user-approved", {"approved": True}, Poison(),
                        {"file": "/private/source.pdf", "bypassScan": True}):
            with self.subTest(request_type=type(request).__name__):
                report = report_protection_block(feature_exception_request=request)
                self.assertIs(report.origin, ProtectionBlockOrigin.FEATURE_EXCEPTION_REJECTED)
                self.assertIsNone(report.scan_status)
                self.assertEqual(report.message, EXCEPTION_REJECTION_MESSAGE)
                self.assertFalse(report.authorizes_open)
                self.assertFalse(report.user_exception_approved)
                self.assertEqual(report.to_dict(), {
                    "origin": "featureExceptionRejected",
                    "scanStatus": None,
                    "message": EXCEPTION_REJECTION_MESSAGE,
                    "authorizesOpen": False,
                    "userExceptionApproved": False,
                })
                self.assertNotIn("private", str(report.to_dict()))

    def test_untrusted_scanner_tokens_remain_failures_when_exception_claimed(self):
        for spoof in ("clean", "userApproved", {"approved": True}, object(),
                      ScanResultStatus.clean, ScannerFailureKind.TIMED_OUT.value):
            with self.subTest(spoof_type=type(spoof).__name__):
                report = report_protection_block(
                    spoof, feature_exception_request={"approved": True})
                self.assertIs(report.origin, ProtectionBlockOrigin.SCANNER_FAILURE)
                self.assertIs(report.scan_status, ScanResultStatus.scanFailed)
                self.assertFalse(report.authorizes_open)
                self.assertFalse(report.user_exception_approved)
                self.assertNotIn("userApproved", report.message)

    def test_no_failure_and_no_request_is_not_an_authorization(self):
        self.assertIsNone(report_protection_block())
        self.assertIsNone(report_protection_block(None, feature_exception_request=None))

    def test_immutable_boundary_rejects_forged_outcomes(self):
        failure = report_protection_block(ScannerFailureKind.TIMED_OUT)
        with self.assertRaises(FrozenInstanceError):
            failure.scan_status = ScanResultStatus.clean
        with self.assertRaises(ValueError):
            replace(failure, scan_status=ScanResultStatus.clean)
        with self.assertRaises(ValueError):
            replace(failure, origin=ProtectionBlockOrigin.FEATURE_EXCEPTION_REJECTED)
        with self.assertRaises(ValueError):
            replace(failure, message="Approved by user")
        with self.assertRaises(ValueError):
            ProtectionBlockReport(ProtectionBlockOrigin.FEATURE_EXCEPTION_REJECTED,
                                  ScanResultStatus.malwareDetected,
                                  EXCEPTION_REJECTION_MESSAGE)
        with self.assertRaises(ValueError):
            ProtectionBlockReport("scannerFailure", ScanResultStatus.scanFailed,
                                  failure.message)

    def test_real_scanner_failure_still_blocks_despite_exception_claim(self):
        spec = importlib.util.spec_from_file_location(
            "opener344_scan_gate", ROOT / "scan-and-open.py")
        gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gate)
        with tempfile.TemporaryDirectory(prefix="opener344-") as directory:
            pdf = Path(directory) / "synthetic.pdf"
            source = b"%PDF-1.4\nUntrusted synthetic fixture\n"
            pdf.write_bytes(source)
            with patch.object(gate, "CACHE_DB", Path(directory) / "cache.sqlite"), \
                 patch.object(gate, "intended_destination", return_value="com.brave.Browser"), \
                 patch.object(gate, "pdf_fallback_application", return_value=None), \
                 patch.object(gate, "record_scan_destination"), \
                 patch.object(gate, "verify_launch_target"), \
                 patch.object(gate, "read_signature_database_version", return_value=None), \
                 patch.object(gate, "run_scan_command",
                              return_value=subprocess.CompletedProcess(
                                  [], 2, "", "/private/runner/scanner failed")), \
                 patch.object(gate, "remember_clean") as clean_cache, \
                 patch.object(gate, "remove_quarantine") as remove_quarantine, \
                 patch.object(gate, "launch_clean_file") as launch:
                with self.assertRaises(RuntimeError):
                    gate.scan_and_open(str(pdf), "/synthetic-scanner")
            report = report_protection_block(
                ScannerFailureKind.PROCESS_FAILED,
                feature_exception_request={"approved": True, "feature": "AcroForm"})
            self.assertIs(report.scan_status, ScanResultStatus.scanFailed)
            self.assertEqual(pdf.read_bytes(), source)
            clean_cache.assert_not_called()
            remove_quarantine.assert_not_called()
            launch.assert_not_called()

    def test_policy_metadata_and_ci_do_not_enable_exceptions(self):
        from protection_profiles import PROTECTION_PROFILES
        from effective_protection_policy import resolve_effective_policy
        self.assertTrue(all(not p.selectable for p in PROTECTION_PROFILES.values()))
        self.assertEqual(resolve_effective_policy().profile_id, "built-in")
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("report_protection_block(", gate)
        self.assertIn("if not cached_clean(cache_id):", gate)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 test-protection-failure-exception-boundary.py -v", ci)


if __name__ == "__main__":
    unittest.main()
