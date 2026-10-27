#!/usr/bin/env python3
"""Verify download-availability checks gate scan, cache, and application launch."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "availability_scan", Path(__file__).with_name("scan-and-open.py"))
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)
UNAVAILABLE = "The requested PDF is not available locally; opening was stopped."


class DownloadAvailabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.pdf = root / "Cloud report.PDF"
        self.pdf.write_bytes(b"%PDF-1.4\nfully local file")
        for name, value in (
            ("CACHE_DB", root / "cache.sqlite3"),
            ("SCAN_REQUEST_DB", root / "request.sqlite3"),
        ):
            setting = patch.object(opener, name, value)
            setting.start()
            self.addCleanup(setting.stop)

    def test_not_downloaded_blocks_before_any_hash_or_scan(self):
        with patch.object(opener, "verify_local_file_available",
                          side_effect=RuntimeError(UNAVAILABLE)) as available, \
             patch.object(opener, "fingerprint") as fingerprint, \
             patch.object(opener, "cached_clean") as cache, \
             patch.object(opener.subprocess, "run") as scan, \
             patch.object(opener, "remove_quarantine") as quarantine, \
             patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "not available locally"):
                opener.scan_and_open(self.pdf, "/scanner")
        available.assert_called_once_with(self.pdf)
        fingerprint.assert_not_called()
        cache.assert_not_called()
        scan.assert_not_called()
        quarantine.assert_not_called()
        launch.assert_not_called()

    def test_downloaded_pdf_opens_only_after_rechecks(self):
        clean = subprocess.CompletedProcess([], 0, "file: OK\n", "")
        with patch.object(opener, "verify_local_file_available") as available, \
             patch.object(opener, "verify_launch_target"), \
             patch.object(opener.subprocess, "run", return_value=clean) as scan, \
             patch.object(opener, "remove_quarantine"), \
             patch.object(opener, "launch_clean_file") as launch:
            result = opener.scan_and_open(self.pdf, "/scanner")
        self.assertEqual(result.status, "clean")
        self.assertEqual(available.call_count, 3)
        scan.assert_called_once()
        launch.assert_called_once()

    def test_eviction_during_scan_blocks_quarantine_and_browser(self):
        clean = subprocess.CompletedProcess([], 0, "file: OK\n", "")
        with patch.object(opener, "verify_local_file_available",
                          side_effect=[None, RuntimeError(UNAVAILABLE)]) as available, \
             patch.object(opener.subprocess, "run", return_value=clean) as scan, \
             patch.object(opener, "verify_launch_target") as target, \
             patch.object(opener, "remove_quarantine") as quarantine, \
             patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "not available locally"):
                opener.scan_and_open(self.pdf, "/scanner")
        self.assertEqual(available.call_count, 2)
        scan.assert_called_once()
        target.assert_not_called()
        quarantine.assert_not_called()
        launch.assert_not_called()

    def test_eviction_after_quarantine_removal_blocks_browser(self):
        clean = subprocess.CompletedProcess([], 0, "file: OK\n", "")
        with patch.object(opener, "verify_local_file_available",
                          side_effect=[None, None, RuntimeError(UNAVAILABLE)]) as available, \
             patch.object(opener.subprocess, "run", return_value=clean), \
             patch.object(opener, "verify_launch_target"), \
             patch.object(opener, "remove_quarantine") as quarantine, \
             patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "not available locally"):
                opener.scan_and_open(self.pdf, "/scanner")
        self.assertEqual(available.call_count, 3)
        quarantine.assert_called_once()
        launch.assert_not_called()

    def test_clean_cache_cannot_bypass_download_check(self):
        clean = subprocess.CompletedProcess([], 0, "file: OK\n", "")
        with patch.object(opener, "verify_local_file_available"), \
             patch.object(opener.subprocess, "run", return_value=clean) as scan, \
             patch.object(opener, "verify_launch_target"), \
             patch.object(opener, "remove_quarantine"), \
             patch.object(opener, "launch_clean_file"):
            opener.scan_and_open(self.pdf, "/scanner")
        scan.assert_called_once()
        with patch.object(opener, "verify_local_file_available",
                          side_effect=RuntimeError(UNAVAILABLE)), \
             patch.object(opener, "cached_clean") as cache, \
             patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "not available locally"):
                opener.scan_and_open(self.pdf, "/scanner")
        cache.assert_not_called()
        launch.assert_not_called()

    def test_pdf_icloud_placeholder_never_reaches_scan_queue(self):
        placeholder = self.pdf.with_name("Report.PDF.icloud")
        placeholder.touch()
        with patch.object(opener, "scan_slot") as slot, \
             patch.object(opener.subprocess, "run") as scan, \
             patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "not available locally"):
                opener.scan_and_open(placeholder, "/scanner")
        slot.assert_not_called()
        scan.assert_not_called()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
