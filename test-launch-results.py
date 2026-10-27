#!/usr/bin/env python3
"""Clean scan results survive destination-application failures."""
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "scan_and_open", Path(__file__).with_name("scan-and-open.py"))
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class LaunchResultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "test.pdf"
        self.file.write_bytes(b"%PDF-1.4\nclean data")
        cache = patch.object(opener, "CACHE_DB",
                             Path(self.temp.name) / "clean-scan-cache.sqlite3")
        cache.start()
        self.addCleanup(cache.stop)
        version = patch.object(opener, 'scan_engine_version', return_value=None)
        version.start()
        self.addCleanup(version.stop)

    def test_launch_failure_keeps_completed_result_and_cache(self):
        raw = subprocess.CompletedProcess([], 0, "file: OK", "")
        launch_error = subprocess.CalledProcessError(1, "/usr/bin/open")
        with patch.object(opener.subprocess, "run", return_value=raw) as scan, \
                patch.object(opener, "remove_quarantine") as quarantine, \
                patch.object(opener, "launch_clean_file",
                             side_effect=launch_error) as launch:
            with self.assertRaises(opener.LaunchFailedError) as raised:
                opener.scan_and_open(str(self.file), "/scanner")
        self.assertEqual(raised.exception.scan_result,
                         opener.CleanScanResult("clean", False))
        self.assertIs(raised.exception.__cause__, launch_error)
        self.assertIn("scan completed cleanly", str(raised.exception))
        scan.assert_called_once()
        quarantine.assert_called_once_with(self.file.resolve())
        launch.assert_called_once_with(self.file.resolve())
        digest = opener.cache_key(opener.fingerprint(self.file), True)
        self.assertTrue(opener.cached_clean(digest))
        self.assertEqual(self.file.read_bytes(), b"%PDF-1.4\nclean data")

    def test_retry_after_launch_failure_reuses_verified_scan(self):
        raw = subprocess.CompletedProcess([], 0, "file: OK", "")
        with patch.object(opener.subprocess, "run", return_value=raw) as scan, \
                patch.object(opener, "remove_quarantine"), \
                patch.object(opener, "launch_clean_file",
                             side_effect=[OSError("destination unavailable"), None]) as launch:
            with self.assertRaises(opener.LaunchFailedError) as raised:
                opener.scan_and_open(str(self.file), "/scanner")
            completed = opener.scan_and_open(str(self.file), "/scanner")
        self.assertEqual(raised.exception.scan_result,
                         opener.CleanScanResult("clean", False))
        self.assertEqual(completed, opener.CleanScanResult("clean", True))
        self.assertEqual(scan.call_count, 1, "Retry must not force a rescan")
        self.assertEqual(launch.call_count, 2)

    def test_cached_clean_launch_failure_preserves_cached_receipt(self):
        digest = opener.cache_key(opener.fingerprint(self.file), True)
        opener.remember_clean(digest)
        with patch.object(opener.subprocess, "run") as scan, \
                patch.object(opener, "remove_quarantine"), \
                patch.object(opener, "launch_clean_file",
                             side_effect=RuntimeError("destination missing")):
            with self.assertRaises(opener.LaunchFailedError) as raised:
                opener.scan_and_open(str(self.file), "/scanner")
        self.assertEqual(raised.exception.scan_result,
                         opener.CleanScanResult("clean", True))
        scan.assert_not_called()
        self.assertTrue(opener.cached_clean(digest))

    def test_blocked_scans_do_not_create_clean_receipts(self):
        for code, output in [(1, "file: Malware FOUND"), (0, "file: Empty file")]:
            self.file.write_bytes(self.file.read_bytes() + bytes([code]))
            raw = subprocess.CompletedProcess([], code, output, "")
            with self.subTest(code=code, output=output), \
                    patch.object(opener.subprocess, "run", return_value=raw), \
                    patch.object(opener, "remove_quarantine") as quarantine, \
                    patch.object(opener, "launch_clean_file") as launch:
                with self.assertRaises(RuntimeError) as raised:
                    opener.scan_and_open(str(self.file), "/scanner")
            self.assertNotIsInstance(raised.exception, opener.LaunchFailedError)
            self.assertFalse(hasattr(raised.exception, "scan_result"))
            quarantine.assert_not_called()
            launch.assert_not_called()

    def test_quarantine_failure_is_not_misclassified_as_launch_failure(self):
        raw = subprocess.CompletedProcess([], 0, "file: OK", "")
        with patch.object(opener.subprocess, "run", return_value=raw), \
                patch.object(opener, "remove_quarantine",
                             side_effect=OSError("xattr failure")), \
                patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(OSError, "xattr failure") as raised:
                opener.scan_and_open(str(self.file), "/scanner")
        self.assertNotIsInstance(raised.exception, opener.LaunchFailedError)
        launch.assert_not_called()

    def test_cli_launch_failure_remains_nonzero_and_private(self):
        raw = subprocess.CompletedProcess([], 0, "file: OK", "")
        stderr = StringIO()
        with patch.object(opener, "scanner_path", return_value="/scanner"), \
                patch.object(opener, "check_database"), \
                patch.object(opener.subprocess, "run", return_value=raw), \
                patch.object(opener, "remove_quarantine"), \
                patch.object(opener, "launch_clean_file",
                             side_effect=FileNotFoundError("destination absent")), \
                patch("sys.stderr", stderr):
            code = opener.main([str(self.file)])
        self.assertEqual(code, 1)
        self.assertIn("The request could not be processed", stderr.getvalue())
        self.assertNotIn("destination absent", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
