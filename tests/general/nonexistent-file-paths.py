#!/usr/bin/env python3
"""opener-0827: reject absent local paths before scanning or opening.

Only disposable temporary files and mocked scanner/launcher boundaries are used.
"""
from contextlib import contextmanager, redirect_stderr
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("missing_path_scan_gate", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)


class NonexistentFilePathTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="opener-0827-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.missing = self.root / "sensitive-looking missing document.pdf"

    def assert_rejected_without_path_disclosure(self, path):
        for validator in (gate.validate_scan_request, gate.supported_request_path):
            with self.subTest(path=path.name, validator=validator.__name__):
                with self.assertRaises(RuntimeError) as failure:
                    validator(path)
                self.assertEqual(str(failure.exception), gate.NONEXISTENT_SCAN_INPUT_MESSAGE)
                self.assertEqual(gate.safe_scan_failure(failure.exception),
                                 gate.NONEXISTENT_SCAN_INPUT_MESSAGE)
                self.assertNotIn(str(path), str(failure.exception))
                self.assertNotIn(path.name, str(failure.exception))

    def test_missing_regular_files_bundles_and_parent_directories(self):
        for path in (
            self.missing,
            self.root / "missing.txt",
            self.root / "Missing.app",
            self.root / "missing-parent" / "report.pdf",
        ):
            self.assert_rejected_without_path_disclosure(path)

    def test_dangling_symlink_cannot_authorize_opening(self):
        alias = self.root / "dangling alias.pdf"
        alias.symlink_to(self.missing)
        self.assert_rejected_without_path_disclosure(alias)

    def test_invalid_only_cli_batch_stops_before_scanner_initialization(self):
        output = io.StringIO()
        with patch.object(gate, "watch_parent_lifetime"), \
                patch.object(gate, "scanner_path") as scanner, \
                patch.object(gate, "check_database") as database, \
                patch.object(gate, "scan_and_open") as scanning, \
                patch.object(gate, "record_scan_request") as audit, \
                redirect_stderr(output):
            code = gate.main([str(self.missing), str(self.root / "missing.txt")])
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue().count(gate.NONEXISTENT_SCAN_INPUT_MESSAGE), 2)
        self.assertNotIn(str(self.root), output.getvalue())
        self.assertNotIn(self.missing.name, output.getvalue())
        scanner.assert_not_called()
        database.assert_not_called()
        scanning.assert_not_called()
        audit.assert_not_called()

    def test_direct_scan_rejects_before_queue_cache_scan_and_launch(self):
        with patch.object(gate, "scan_slot") as queue, \
                patch.object(gate, "cached_clean") as cache, \
                patch.object(gate, "run_scan_command") as scanner, \
                patch.object(gate, "verify_launch_target") as verify, \
                patch.object(gate, "launch_clean_file") as launcher, \
                patch.object(gate, "remove_quarantine") as quarantine:
            with self.assertRaises(RuntimeError) as failure:
                gate.scan_and_open(str(self.missing), "/scanner")
        self.assertEqual(str(failure.exception), gate.NONEXISTENT_SCAN_INPUT_MESSAGE)
        for mocked in (queue, cache, scanner, verify, launcher, quarantine):
            mocked.assert_not_called()

    def test_removed_after_initial_validation_still_fails_secondary_gate(self):
        transient = self.root / "disappearing.pdf"
        transient.write_bytes(b"%PDF-1.4\nnot-a-real-document\n")
        @contextmanager
        def remove_before_secondary_admission():
            transient.unlink()
            yield

        with patch.object(gate, "scan_slot", return_value=remove_before_secondary_admission()), \
                patch.object(gate, "cached_clean") as cache, \
                patch.object(gate, "run_scan_command") as scanner, \
                patch.object(gate, "launch_clean_file") as launcher, \
                patch.object(gate, "remember_clean") as remember:
            with self.assertRaises(RuntimeError) as failure:
                gate.scan_and_open(transient, "/scanner")
        self.assertEqual(str(failure.exception), gate.NONEXISTENT_SCAN_INPUT_MESSAGE)
        cache.assert_not_called()
        scanner.assert_not_called()
        launcher.assert_not_called()
        remember.assert_not_called()

    def test_existing_file_and_valid_symlink_still_pass_admission(self):
        existing = self.root / "valid.pdf"
        original = b"%PDF-1.4\nsynthetic\n"
        existing.write_bytes(original)
        alias = self.root / "valid alias.pdf"
        alias.symlink_to(existing)
        for path in (existing, alias):
            with self.subTest(path=path.name):
                self.assertEqual(gate.validate_scan_request(path), existing)
                self.assertEqual(gate.supported_request_path(path), existing)
        self.assertEqual(existing.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
