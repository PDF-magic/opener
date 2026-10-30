#!/usr/bin/env python3
"""Regression coverage for locally available PDFs in iCloud Drive paths.

Use a temporary directory that mirrors the normal macOS iCloud Drive layout;
never read, download, or modify a user's actual iCloud documents.
"""

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "scan_and_open", (Path(__file__).resolve().parents[2]s[2] / "scan-and-open.py"))
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class ICloudDriveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.drive = root / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
        folder = self.drive / "Shared Projects" / "Résumé"
        folder.mkdir(parents=True)
        self.pdf = folder / "Quarterly report 2026.pdf"
        self.content = b"%PDF-1.4\nlocally available document\n"
        self.pdf.write_bytes(self.content)

        for attribute, value in (
            ("CACHE_DB", root / "clean-scans.sqlite3"),
            ("SCAN_REQUEST_DB", root / "scan-requests.sqlite3"),
        ):
            setting = patch.object(opener, attribute, value)
            setting.start()
            self.addCleanup(setting.stop)
        destination = patch.object(opener, "intended_destination",
                                   return_value="com.apple.Preview")
        destination.start()
        self.addCleanup(destination.stop)
        version = patch.object(opener, "scan_engine_version", return_value=None)
        version.start()
        self.addCleanup(version.stop)

    def test_local_icloud_pdf_uses_full_scan_and_configured_pdf_destination(self):
        clean = subprocess.CompletedProcess([], 0, "file: OK", "")
        with patch.object(opener.subprocess, "run", return_value=clean) as scan, \
                patch.object(opener, "verify_launch_target") as verify, \
                patch.object(opener, "remove_quarantine") as quarantine, \
                patch.object(opener, "launch_clean_file") as launch:
            result = opener.scan_and_open(self.pdf, "/scanner")

        self.assertEqual(result.status, "clean")
        self.assertFalse(result.from_cache)
        scan.assert_called_once()
        command = scan.call_args.args[0]
        self.assertEqual(command[0], "/scanner")
        self.assertEqual(command[-1], str(self.pdf.resolve()))
        self.assertIn("--max-filesize=0", command)
        verify.assert_called_once_with(self.pdf.resolve(),
                                       target_app="com.apple.Preview")
        quarantine.assert_called_once_with(self.pdf.resolve())
        launch.assert_called_once_with(self.pdf.resolve(),
                                       target_app="com.apple.Preview")
        self.assertEqual(self.pdf.read_bytes(), self.content)

    def test_icloud_path_through_local_symlink_alias_reuses_verdict(self):
        alias = Path(self.temp.name) / "iCloud Drive Alias"
        alias.symlink_to(self.drive, target_is_directory=True)
        selected = alias / "Shared Projects" / "Résumé" / self.pdf.name
        clean = subprocess.CompletedProcess([], 0, "file: OK", "")
        with patch.object(opener.subprocess, "run", return_value=clean) as scan, \
                patch.object(opener, "verify_launch_target"), \
                patch.object(opener, "remove_quarantine"), \
                patch.object(opener, "launch_clean_file") as launch:
            first = opener.scan_and_open(self.pdf, "/scanner")
            second = opener.scan_and_open(selected, "/scanner")

        self.assertFalse(first.from_cache)
        self.assertTrue(second.from_cache)
        scan.assert_called_once()
        self.assertEqual(launch.call_count, 2)
        self.assertEqual(launch.call_args.args[0], self.pdf.resolve())

    def test_missing_local_icloud_pdf_does_not_trigger_scan_or_launch(self):
        not_downloaded = self.pdf.with_name("cloud-only.pdf")
        with patch.object(opener.subprocess, "run") as scan, \
                patch.object(opener, "remove_quarantine") as quarantine, \
                patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaises((OSError, RuntimeError)):
                opener.scan_and_open(not_downloaded, "/scanner")
        scan.assert_not_called()
        quarantine.assert_not_called()
        launch.assert_not_called()

    def test_icloud_pdf_malware_verdict_blocks_quarantine_and_launch(self):
        infected = subprocess.CompletedProcess([], 1, "file: Example.Malware FOUND", "")
        with patch.object(opener.subprocess, "run", return_value=infected) as scan, \
                patch.object(opener, "remove_quarantine") as quarantine, \
                patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "Malware"):
                opener.scan_and_open(self.pdf, "/scanner")
        scan.assert_called_once()
        quarantine.assert_not_called()
        launch.assert_not_called()
        self.assertEqual(self.pdf.read_bytes(), self.content)


if __name__ == "__main__":
    unittest.main()
