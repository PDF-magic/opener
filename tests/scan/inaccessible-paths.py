#!/usr/bin/env python3
"""Reject inaccessible local scan selections without scanner or launch side effects."""

import importlib.util
import io
import os
from contextlib import redirect_stderr
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "inaccessible_path_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class InaccessibleScanPathTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inaccessible-path-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / "private document.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nunchanged document")
        self.bundle = self.root / "Unreadable.app"
        self.bundle.mkdir()

    def denied_bundle_enumeration(self):
        original = os.scandir

        def scandir(path):
            if os.fspath(path) == os.fspath(self.bundle):
                raise PermissionError("Private source path: permission denied")
            return original(path)

        return patch.object(gate.os, "scandir", side_effect=scandir)

    def assert_no_scan_effects(self, selection):
        with patch.object(gate, "scan_slot") as queue, \
                patch.object(gate, "cached_clean") as cache, \
                patch.object(gate, "run_scan_command") as scanner, \
                patch.object(gate, "launch_clean_file") as launch, \
                patch.object(gate, "remove_quarantine") as quarantine:
            with self.assertRaises((OSError, RuntimeError)):
                gate.scan_and_open(selection, "/scanner")
        queue.assert_not_called()
        cache.assert_not_called()
        scanner.assert_not_called()
        launch.assert_not_called()
        quarantine.assert_not_called()
        self.assertEqual(self.pdf.read_bytes(), b"%PDF-1.4\nunchanged document")

    def test_missing_file_and_broken_symlink_fail_before_any_scan(self):
        absent = self.root / "missing.pdf"
        broken = self.root / "broken.pdf"
        broken.symlink_to(absent)
        for selection in (absent, broken):
            with self.subTest(selection=selection.name):
                for validate in (gate.validate_scan_request, gate.supported_request_path):
                    with self.assertRaises((OSError, RuntimeError)):
                        validate(selection)
                self.assert_no_scan_effects(selection)

    def test_permission_denied_during_path_resolution_never_scans(self):
        original = Path.resolve

        def deny_selected(path, *args, **kwargs):
            if path == self.pdf:
                raise PermissionError("Private source path: no search permission")
            return original(path, *args, **kwargs)

        with patch.object(Path, "resolve", deny_selected):
            for validate in (gate.validate_scan_request, gate.supported_request_path):
                with self.subTest(validate=validate.__name__):
                    with self.assertRaises(PermissionError):
                        validate(self.pdf)
            self.assert_no_scan_effects(self.pdf)

    def test_inaccessible_app_directory_rejected_by_both_admission_gates(self):
        with self.denied_bundle_enumeration():
            for validate in (gate.validate_scan_request, gate.supported_request_path):
                with self.subTest(validate=validate.__name__):
                    with self.assertRaises(RuntimeError) as result:
                        validate(self.bundle)
                    self.assertEqual(str(result.exception),
                                     gate.UNREADABLE_SCAN_INPUT_MESSAGE)
                    self.assertEqual(gate.safe_scan_failure(result.exception),
                                     gate.UNREADABLE_SCAN_INPUT_MESSAGE)
            self.assert_no_scan_effects(self.bundle)

    def test_inaccessible_app_preflight_stops_before_scanner_initialization(self):
        output = io.StringIO()
        with self.denied_bundle_enumeration(), \
                patch.object(gate, "watch_parent_lifetime"), \
                patch.object(gate, "scanner_path") as scanner, \
                patch.object(gate, "check_database") as database, \
                patch.object(gate, "scan_and_open") as scan, \
                redirect_stderr(output):
            self.assertEqual(gate.main([str(self.bundle)]), 1)
        scanner.assert_not_called()
        database.assert_not_called()
        scan.assert_not_called()
        self.assertIn(gate.UNREADABLE_SCAN_INPUT_MESSAGE, output.getvalue())
        self.assertNotIn(str(self.bundle), output.getvalue())

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permissions")
    def test_real_unreadable_bundle_directory_is_rejected(self):
        self.bundle.chmod(0)
        try:
            for validate in (gate.validate_scan_request, gate.supported_request_path):
                with self.subTest(validate=validate.__name__):
                    with self.assertRaises((OSError, RuntimeError)):
                        validate(self.bundle)
            self.assert_no_scan_effects(self.bundle)
        finally:
            self.bundle.chmod(0o700)

    def test_existing_file_alias_and_readable_app_remain_supported(self):
        alias = self.root / "linked document.pdf"
        alias.symlink_to(self.pdf)
        for validate in (gate.validate_scan_request, gate.supported_request_path):
            with self.subTest(validate=validate.__name__):
                self.assertEqual(validate(alias), self.pdf)
                self.assertEqual(validate(self.bundle), self.bundle)
        with self.assertRaises(RuntimeError):
            gate.supported_request_path(self.root)


if __name__ == "__main__":
    unittest.main()
