#!/usr/bin/env python3
"""opener-0844: fail closed when a selected file vanishes during a scan.

Use disposable synthetic PDFs and mocked scanner/launch boundaries only.
"""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("midscan_unavailable_gate",
                                               ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class UnavailableDuringScanTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-0844-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.pdf = self.root / "private user-selected.pdf"
        self.contents = b"%PDF-1.4\nSynthetic document, not user content.\n"
        self.pdf.write_bytes(self.contents)

    def scan_context(self):
        """Stub side effects but keep real admission, hashing and identity checks."""
        from contextlib import ExitStack
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(gate, "scan_slot", return_value=nullcontext()))
        stack.enter_context(patch.object(gate, "active_scan_lock", return_value=nullcontext()))
        stack.enter_context(patch.object(gate, "cached_clean", return_value=False))
        stack.enter_context(patch.object(gate, "verify_local_file_available"))
        stack.enter_context(patch.object(gate, "intended_destination",
                                         return_value="com.brave.Browser"))
        stack.enter_context(patch.object(gate, "pdf_fallback_application",
                                         return_value=None))
        stack.enter_context(patch.object(gate, "record_scan_destination"))
        stack.enter_context(patch.object(gate, "read_signature_database_version",
                                         return_value=None))
        self.remember = stack.enter_context(patch.object(gate, "remember_clean"))
        self.launch = stack.enter_context(patch.object(gate, "launch_clean_file"))
        self.quarantine = stack.enter_context(patch.object(gate, "remove_quarantine"))
        self.origin = stack.enter_context(patch.object(gate, "record_opened_document_origin"))
        self.version = stack.enter_context(patch.object(gate, "scan_engine_version",
                                                       return_value="1.4.3"))
        return stack

    def assert_unavailable_without_release(self, operation):
        with self.assertRaises(RuntimeError) as result:
            operation()
        self.assertEqual(str(result.exception),
                         gate.SCAN_INPUT_BECAME_UNAVAILABLE_MESSAGE)
        self.assertEqual(gate.safe_scan_failure(result.exception),
                         gate.SCAN_INPUT_BECAME_UNAVAILABLE_MESSAGE)
        self.assertNotIn(str(self.root), str(result.exception))
        self.remember.assert_not_called()
        self.launch.assert_not_called()
        self.quarantine.assert_not_called()
        self.origin.assert_not_called()
        self.version.assert_not_called()

    def test_missing_file_after_clean_scanner_response_is_not_cached_or_opened(self):
        self.scan_context()
        def finished_scan(command, timeout):
            self.pdf.unlink()
            return subprocess.CompletedProcess(command, 0, str(self.pdf) + ": OK\n", "")
        with patch.object(gate, "run_scan_command", side_effect=finished_scan) as scanner:
            self.assert_unavailable_without_release(
                lambda: gate.scan_and_open(self.pdf, "/scanner"))
        scanner.assert_called_once()
        self.assertFalse(self.pdf.exists())

    def test_missing_file_after_detection_is_not_misreported_as_malware(self):
        self.scan_context()
        def finished_scan(command, timeout):
            self.pdf.unlink()
            return subprocess.CompletedProcess(
                command, 1, str(self.pdf) + ": Malware FOUND\n", "")
        with patch.object(gate, "run_scan_command", side_effect=finished_scan) as scanner:
            self.assert_unavailable_without_release(
                lambda: gate.scan_and_open(self.pdf, "/scanner"))
        scanner.assert_called_once()

    def test_permission_loss_after_scanner_response_is_sanitized(self):
        self.scan_context()
        file_identity = gate.file_identity
        state = {"unavailable": False}
        def changed_permissions(path, *args, **kwargs):
            if state["unavailable"]:
                raise PermissionError(str(self.pdf) + ": denied during scan")
            return file_identity(path, *args, **kwargs)
        def completed_scan(command, timeout):
            state["unavailable"] = True
            return subprocess.CompletedProcess(command, 0, str(self.pdf) + ": OK\n", "")
        with patch.object(gate, "file_identity", side_effect=changed_permissions), \
                patch.object(gate, "run_scan_command", side_effect=completed_scan):
            self.assert_unavailable_without_release(
                lambda: gate.scan_and_open(self.pdf, "/scanner"))
        self.assertEqual(self.pdf.read_bytes(), self.contents)

    def test_cached_verdict_does_not_open_if_file_becomes_unavailable(self):
        self.scan_context()
        def cached_then_deleted(_digest):
            self.pdf.unlink()
            return True
        with patch.object(gate, "cached_clean", side_effect=cached_then_deleted), \
                patch.object(gate, "cached_scan") as cached_result, \
                patch.object(gate, "run_scan_command") as scanner:
            self.assert_unavailable_without_release(
                lambda: gate.scan_and_open(self.pdf, "/scanner"))
        cached_result.assert_not_called()
        scanner.assert_not_called()

    def test_file_deleted_during_direct_integrity_check_uses_fixed_message(self):
        original_digest = gate.fingerprint(self.pdf)
        original_identity = gate.file_identity(self.pdf)
        self.pdf.unlink()
        # The independent network-volume preflight intentionally rejects a
        # vanished path first. Isolate the content/identity check so this test
        # verifies its own error translation, not the mounted-volume contract.
        with patch.object(gate, "require_accessible_volume"), \
                self.assertRaises(RuntimeError) as result:
            gate.verify_file_integrity(self.pdf, original_digest, original_identity)
        self.assertEqual(str(result.exception),
                         gate.SCAN_INPUT_BECAME_UNAVAILABLE_MESSAGE)

    def test_unchanged_clean_scan_still_allows_normal_handoff(self):
        self.scan_context()
        with patch.object(gate, "run_scan_command",
                          return_value=subprocess.CompletedProcess(
                              [], 0, str(self.pdf) + ": OK\n", "")) as scanner, \
                patch.object(gate, "verify_launch_target"):
            verdict = gate.scan_and_open(self.pdf, "/scanner")
        self.assertEqual(verdict.status, "clean")
        self.assertFalse(verdict.from_cache)
        scanner.assert_called_once()
        self.remember.assert_called_once()
        self.launch.assert_called_once()
        self.assertEqual(self.pdf.read_bytes(), self.contents)


if __name__ == "__main__":
    unittest.main()
