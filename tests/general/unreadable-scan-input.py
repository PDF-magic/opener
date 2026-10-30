#!/usr/bin/env python3
"""Unreadable scan-input regression coverage (opener-0366)."""

import importlib.util
import io
from contextlib import nullcontext, redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "unreadable_scan_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FailingReader:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        raise OSError("Private original filepath: source cannot be read")


class UnreadableScanInputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="unreadable-scan-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.pdf = self.root / "private $document & report.pdf"
        self.contents = b"%PDF-1.4\nreadable document"
        self.pdf.write_bytes(self.contents)

    def mock_file_open(self, target, *, fail_after=0, read_failure=False):
        original = Path.open
        calls = [0]

        def guarded_open(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get("mode", "r")
            if path == target and mode == "rb":
                calls[0] += 1
                if calls[0] > fail_after:
                    if read_failure:
                        return FailingReader()
                    raise PermissionError("Private filename: access denied")
            return original(path, *args, **kwargs)

        return patch.object(Path, "open", guarded_open)

    def test_file_open_denial_blocks_both_request_admission_paths(self):
        with self.mock_file_open(self.pdf):
            for validator in (gate.validate_scan_request, gate.supported_request_path):
                with self.subTest(validator=validator.__name__):
                    with self.assertRaises(RuntimeError) as failure:
                        validator(self.pdf)
                    self.assertEqual(str(failure.exception),
                                     gate.UNREADABLE_SCAN_INPUT_MESSAGE)
                    self.assertEqual(gate.safe_scan_failure(failure.exception),
                                     gate.UNREADABLE_SCAN_INPUT_MESSAGE)
                    self.assertNotIn(str(self.pdf), str(failure.exception))
        self.assertEqual(self.pdf.read_bytes(), self.contents)

    def test_unreadable_input_is_rejected_before_scanner_initialization(self):
        output = io.StringIO()
        with self.mock_file_open(self.pdf), \
                patch.object(gate, "watch_parent_lifetime"), \
                patch.object(gate, "scanner_path") as scanner, \
                patch.object(gate, "check_database") as signatures, \
                patch.object(gate, "scan_and_open") as scan, \
                redirect_stderr(output):
            self.assertEqual(gate.main([str(self.pdf)]), 1)
        scanner.assert_not_called()
        signatures.assert_not_called()
        scan.assert_not_called()
        self.assertIn(gate.UNREADABLE_SCAN_INPUT_MESSAGE, output.getvalue())
        self.assertNotIn(str(self.pdf), output.getvalue())
        self.assertNotIn(self.pdf.name, output.getvalue())

    def test_unreadable_input_does_not_enter_scan_queue_or_cache(self):
        with self.mock_file_open(self.pdf), \
                patch.object(gate, "scan_slot") as queue, \
                patch.object(gate, "cached_clean") as cached, \
                patch.object(gate, "run_scan_command") as scan, \
                patch.object(gate, "launch_clean_file") as launch, \
                patch.object(gate, "remove_quarantine") as quarantine:
            with self.assertRaisesRegex(RuntimeError, "unreadable"):
                gate.scan_and_open(str(self.pdf), "/scanner")
        queue.assert_not_called()
        cached.assert_not_called()
        scan.assert_not_called()
        launch.assert_not_called()
        quarantine.assert_not_called()

    def test_read_failure_during_fingerprint_is_not_a_clean_verdict(self):
        with self.mock_file_open(self.pdf, read_failure=True):
            with self.assertRaises(RuntimeError) as failure:
                gate.fingerprint(self.pdf)
        self.assertEqual(str(failure.exception), gate.UNREADABLE_SCAN_INPUT_MESSAGE)

    def test_permission_revoked_after_admission_still_blocks_opening(self):
        # supported_request_path and validate_scan_request both succeed, but
        # the next read of the actual contents fails before cache or ClamAV.
        with self.mock_file_open(self.pdf, fail_after=2, read_failure=True), \
                patch.object(gate, "scan_slot", return_value=nullcontext()), \
                patch.object(gate, "verify_local_file_available"), \
                patch.object(gate, "intended_destination", return_value="com.brave.Browser"), \
                patch.object(gate, "pdf_fallback_application", return_value=None), \
                patch.object(gate, "record_scan_destination"), \
                patch.object(gate, "cached_clean") as cached, \
                patch.object(gate, "run_scan_command") as scan, \
                patch.object(gate, "launch_clean_file") as launch:
            with self.assertRaises(RuntimeError) as failure:
                gate.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(str(failure.exception), gate.UNREADABLE_SCAN_INPUT_MESSAGE)
        cached.assert_not_called()
        scan.assert_not_called()
        launch.assert_not_called()

    def test_unreadable_member_of_app_bundle_cannot_be_hashed(self):
        bundle = self.root / "Example.app"
        member = bundle / "Contents" / "MacOS" / "viewer"
        member.parent.mkdir(parents=True)
        member.write_bytes(b"test executable")
        with self.mock_file_open(member, read_failure=True):
            with self.assertRaises(RuntimeError) as failure:
                gate.fingerprint(bundle)
        self.assertEqual(str(failure.exception), gate.UNREADABLE_SCAN_INPUT_MESSAGE)

    def test_readable_files_and_symlink_aliases_remain_supported(self):
        alias = self.root / "original-name.pdf"
        alias.symlink_to(self.pdf)
        self.assertEqual(gate.validate_scan_request(alias), self.pdf)
        self.assertEqual(gate.supported_request_path(alias), self.pdf)
        self.assertEqual(gate.validate_scan_request(self.pdf), self.pdf)
        self.assertEqual(self.pdf.read_bytes(), self.contents)


if __name__ == "__main__":
    unittest.main()
