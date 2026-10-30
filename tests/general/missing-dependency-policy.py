#!/usr/bin/env python3
"""Regression contract for missing protection dependencies (opener-0256)."""

from contextlib import redirect_stderr
from dataclasses import FrozenInstanceError, replace
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from missing_dependency_policy import (
    MISSING_DEPENDENCY_RESPONSES,
    UNKNOWN_MISSING_DEPENDENCY_RESPONSE,
    MissingDependencyDisposition,
    MissingDependencyResponse,
    response_for_missing_dependency,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS, ControlAvailability, PROTECTION_POLICIES, PolicyControl,
)
from scan_results import ScanResultStatus

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "missing_dependency_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class MissingDependencyPolicyTests(unittest.TestCase):
    def test_every_control_has_immutable_non_clean_response(self):
        self.assertEqual(set(MISSING_DEPENDENCY_RESPONSES), set(PolicyControl))
        self.assertEqual(len(BASELINE_CONTROLS), 4)
        partial = {
            PolicyControl.FILE_INTEGRITY,
            PolicyControl.PDF_STRUCTURE_VALIDATION,
            PolicyControl.ISOLATED_BEHAVIOR_ANALYSIS,
        }
        for control in PolicyControl:
            with self.subTest(control=control.value):
                response = response_for_missing_dependency(control)
                self.assertIs(response, MISSING_DEPENDENCY_RESPONSES[control])
                expected = (ScanResultStatus.incompleteScan if control in partial
                            else ScanResultStatus.scanFailed)
                self.assertIs(response.scan_status, expected)
                self.assertFalse(response.scan_status.permits_open)
                self.assertIs(response.disposition, MissingDependencyDisposition.DENY)
                for flag in ("allow_open", "allow_clean_cache",
                             "allow_quarantine_release", "allow_fallback",
                             "allow_override", "retry_automatically"):
                    self.assertIs(getattr(response, flag), False)
                self.assertIs(response.preserve_quarantine, True)
                self.assertIs(response.show_failure_alert, True)
                self.assertIn("opening was stopped", response.user_message)
                self.assertNotIn("/", response.user_message)
                self.assertNotIn("\\", response.user_message)
                self.assertNotIn("malware detected", response.user_message.lower())
                doc = json.loads(json.dumps(response.as_document()))
                self.assertEqual(doc["scan_status"], expected.value)
                self.assertEqual(doc["control"], control.value)
                self.assertFalse(doc["allow_open"])

    def test_planned_checks_are_not_activated_or_optional_checks_bypassed(self):
        for policy in PROTECTION_POLICIES.values():
            with self.subTest(profile=policy.profile_id.value):
                self.assertFalse(policy.selectable)
                self.assertTrue(all(item.control in MISSING_DEPENDENCY_RESPONSES
                                    for item in policy.requirements))
                for item in policy.requirements:
                    if item.availability is ControlAvailability.PLANNED:
                        self.assertIs(
                            response_for_missing_dependency(item.control).disposition,
                            MissingDependencyDisposition.DENY,
                        )
        for control in BASELINE_CONTROLS:
            self.assertIs(response_for_missing_dependency(control).disposition,
                          MissingDependencyDisposition.DENY)

    def test_untrusted_dependency_values_default_to_refusal(self):
        for bad in ("clamav_scan_gate", "clean", None, 0, True, [],
                    {"control": "clamav_scan_gate"}, object()):
            with self.subTest(input=repr(bad)):
                response = response_for_missing_dependency(bad)
                self.assertIs(response, UNKNOWN_MISSING_DEPENDENCY_RESPONSE)
                self.assertIs(response.scan_status, ScanResultStatus.scanFailed)
                self.assertFalse(response.allow_open)
                self.assertTrue(response.preserve_quarantine)
                if isinstance(bad, str) and bad:
                    self.assertNotIn(bad, response.user_message)

    def test_frozen_registry_rejects_weakening_and_private_messages(self):
        original = response_for_missing_dependency(PolicyControl.CLAMAV_SCAN_GATE)
        with self.assertRaises(FrozenInstanceError):
            original.allow_open = True
        with self.assertRaises(TypeError):
            MISSING_DEPENDENCY_RESPONSES[PolicyControl.CLAMAV_SCAN_GATE] = original
        for flag in ("allow_open", "allow_clean_cache", "allow_quarantine_release",
                     "allow_fallback", "allow_override", "retry_automatically"):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                replace(original, **{flag: True})
        for flag in ("show_failure_alert", "preserve_quarantine"):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                replace(original, **{flag: False})
        for change in (
            {"scan_status": ScanResultStatus.clean},
            {"scan_status": ScanResultStatus.cancelled},
            {"scan_status": "scanFailed"},
            {"user_message": "/private/confidential.pdf: scanner failed"},
            {"user_message": "Malware was detected; opening was stopped."},
            {"control": PolicyControl.SIGNATURE_FRESHNESS},
            {"disposition": "deny"},
        ):
            with self.subTest(change=change), self.assertRaises((TypeError, ValueError)):
                replace(original, **change)
        with self.assertRaises(TypeError):
            MissingDependencyResponse(
                "clamav_scan_gate", ScanResultStatus.scanFailed, original.user_message
            )
        detached = original.as_document()
        detached["allow_open"] = True
        self.assertFalse(original.as_document()["allow_open"])

    def test_missing_clamav_binary_blocks_before_scan_or_quarantine(self):
        with patch.object(gate.os, "access", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "ClamAV is unavailable"):
                gate.scanner_path()
        with tempfile.TemporaryDirectory() as work:
            pdf = Path(work) / "document.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            with patch.object(
                gate, "scanner_path",
                side_effect=RuntimeError(
                    "ClamAV is unavailable. Run the Allow and Open installer again."
                ),
            ), patch.object(gate, "scan_and_open") as scan, \
                    patch.object(gate, "remove_quarantine") as remove, \
                    redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(gate.main([str(pdf)]), 1)
                scan.assert_not_called()
                remove.assert_not_called()
                self.assertIn("ClamAV is unavailable", stderr.getvalue())

    def test_missing_signatures_block_before_scan_or_quarantine(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            pdf = root / "document.pdf"
            pdf.write_bytes(b"%PDF-1.4\n")
            with patch.object(gate, "STAMP", root / "missing-signature-stamp"), \
                    patch.object(gate, "scanner_path", return_value="/mock/clamscan"), \
                    patch.object(gate, "scan_and_open") as scan, \
                    patch.object(gate, "remove_quarantine") as remove, \
                    redirect_stderr(io.StringIO()) as stderr:
                self.assertEqual(gate.main([str(pdf)]), 1)
                scan.assert_not_called()
                remove.assert_not_called()
                self.assertIn("Malware signatures are unavailable", stderr.getvalue())

    def test_declarative_contract_does_not_modify_active_scanning(self):
        installed_gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertNotIn("from missing_dependency_policy import", installed_gate)
        self.assertIn("scanner = scanner_path()", installed_gate)
        self.assertIn("check_database()", installed_gate)
        self.assertIn("if not cached_clean(cache_id):", installed_gate)
        self.assertIn("verify_file_integrity(path, before, identity)", installed_gate)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/run-test.py tests/general/missing-dependency-policy.py -v", ci)
        self.assertIn("python3 scripts/run-test.py tests/scan/and-open.py", ci)
        self.assertIn("macos-build:", ci)


if __name__ == "__main__":
    unittest.main()
