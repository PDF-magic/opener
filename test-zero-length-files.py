#!/usr/bin/env python3
"""Regression tests for zero-length inputs at the installed ClamAV scan gate."""
from contextlib import nullcontext
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "zero_length_scan_gate", Path(__file__).with_name("scan-and-open.py")
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

ERROR = "A zero-length file cannot be scanned; opening was stopped."


class ZeroLengthFileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="zero-length-scanner-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stub("CACHE_DB", self.root / "clean-cache.sqlite3")
        self.stub("SCAN_REQUEST_DB", self.root / "scan-requests.sqlite3")
        self.stub("verify_local_file_available")
        self.stub("intended_destination", return_value="com.brave.Browser")
        self.stub("pdf_fallback_application", return_value=None)
        self.stub("record_scan_destination")
        self.stub("scan_slot", return_value=nullcontext())
        self.stub("read_signature_database_version", return_value=None)
        self.stub("scan_engine_version", return_value=None)
        self.scanner = self.stub("run_scan_command")
        self.cached = self.stub("cached_clean")
        self.quarantine = self.stub("remove_quarantine")
        self.launch = self.stub("launch_clean_file")
        self.verify = self.stub("verify_launch_target")

    def stub(self, name, *args, **kwargs):
        p = patch.object(gate, name, *args, **kwargs)
        value = p.start()
        self.addCleanup(p.stop)
        return value

    def assert_never_scanned_or_opened(self):
        self.scanner.assert_not_called()
        self.cached.assert_not_called()
        self.quarantine.assert_not_called()
        self.launch.assert_not_called()
        self.verify.assert_not_called()

    def test_empty_pdf_and_non_pdf_fail_before_scan_or_cache(self):
        for suffix in (".pdf", ".txt"):
            with self.subTest(suffix=suffix):
                file = self.root / ("private-input" + suffix)
                file.write_bytes(b"")
                with self.assertRaisesRegex(RuntimeError, "zero-length") as caught:
                    gate.scan_and_open(file, "/scanner")
                self.assertEqual(str(caught.exception), ERROR)
                self.assertNotIn(str(file), str(caught.exception))
                self.assertEqual(gate.safe_scan_failure(caught.exception), ERROR)
                self.assert_never_scanned_or_opened()
                self.assertEqual(file.read_bytes(), b"")

    def test_empty_member_of_application_bundle_is_rejected(self):
        bundle = self.root / "Example.app"
        (bundle / "Contents").mkdir(parents=True)
        (bundle / "Contents" / "program").write_bytes(b"nonempty")
        empty = bundle / "Contents" / "empty-resource.pdf"
        empty.write_bytes(b"")
        with self.assertRaisesRegex(RuntimeError, "zero-length"):
            gate.scan_and_open(bundle, "/scanner")
        self.assert_never_scanned_or_opened()
        self.assertEqual(empty.read_bytes(), b"")

    def test_symlink_to_empty_file_does_not_bypass_check(self):
        target = self.root / "empty-target.pdf"
        target.touch()
        alias = self.root / "alias.pdf"
        alias.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "zero-length"):
            gate.scan_and_open(alias, "/scanner")
        self.assert_never_scanned_or_opened()

    def test_empty_file_does_not_use_a_preexisting_clean_receipt(self):
        file = self.root / "already-cached.pdf"
        file.touch()
        self.cached.return_value = True
        with self.assertRaisesRegex(RuntimeError, "zero-length"):
            gate.scan_and_open(file, "/scanner")
        self.assert_never_scanned_or_opened()

    def test_file_becoming_empty_during_scan_stops_before_caching_or_handoff(self):
        file = self.root / "changed-during-scan.pdf"
        file.write_bytes(b"%PDF-1.4\noriginal")
        self.cached.return_value = False
        def change_file(command, timeout):
            file.write_bytes(b"")
            return subprocess.CompletedProcess(command, 0, "file: OK", "")
        self.scanner.side_effect = change_file
        with self.assertRaisesRegex(RuntimeError, "zero-length"):
            gate.scan_and_open(file, "/scanner")
        self.scanner.assert_called_once()
        self.quarantine.assert_not_called()
        self.launch.assert_not_called()
        self.assertEqual(file.read_bytes(), b"")
        self.assertFalse(gate.CACHE_DB.exists(), "changed file must not create a clean receipt")

    def test_nonempty_file_still_uses_existing_scanner(self):
        file = self.root / "nonempty.txt"
        file.write_bytes(b"x")
        self.cached.return_value = False
        self.scanner.return_value = subprocess.CompletedProcess(
            [], 0, "file: OK", ""
        )
        receipt = gate.scan_and_open(file, "/scanner")
        self.assertEqual(receipt.status, "clean")
        self.assertFalse(receipt.from_cache)
        self.scanner.assert_called_once()
        self.launch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
