#!/usr/bin/env python3
"""Exercise the full scan gate against mounted-volume-style PDF paths."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "external_volume_scan", (Path(__file__).resolve().parents[2] / "scan-and-open.py"))
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class ExternalDrivePDFTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.document = root / "Volumes" / "External SSD" / "Report – 2026.PDF"
        self.document.parent.mkdir(parents=True)
        self.document.write_bytes(b"%PDF-1.4\nExternal volume")
        for name, value in (
            ("CACHE_DB", root / "clean-cache.sqlite3"),
            ("SCAN_REQUEST_DB", root / "scan-requests.sqlite3"),
        ):
            setting = patch.object(opener, name, value)
            setting.start()
            self.addCleanup(setting.stop)

    def test_mounted_external_pdf_runs_through_scan_and_selected_app(self):
        completed = subprocess.CompletedProcess([], 0, "volume.pdf: OK\n", "")
        with patch.object(opener.subprocess, "run", return_value=completed) as scan, \
             patch.object(opener, "verify_launch_target") as verify, \
             patch.object(opener, "remove_quarantine") as quarantine, \
             patch.object(opener, "launch_clean_file") as launch:
            result = opener.scan_and_open(self.document, "/scanner")

        self.assertEqual(result.status, "clean")
        self.assertEqual(scan.call_args_list[0].args[0][-1], str(self.document))
        self.assertIn("--max-filesize=0", scan.call_args_list[0].args[0])
        verify.assert_called_once_with(self.document, target_app="com.brave.Browser")
        quarantine.assert_called_once_with(self.document)
        launch.assert_called_once_with(self.document, target_app="com.brave.Browser")

    def test_symlink_to_external_pdf_resolves_to_scanned_file(self):
        shortcut = self.document.parents[2] / "external report alias.pdf"
        shortcut.symlink_to(self.document)
        completed = subprocess.CompletedProcess([], 0, "volume.pdf: OK\n", "")
        with patch.object(opener.subprocess, "run", return_value=completed) as scan, \
             patch.object(opener, "verify_launch_target"), \
             patch.object(opener, "remove_quarantine"), \
             patch.object(opener, "launch_clean_file") as launch:
            opener.scan_and_open(shortcut, "/scanner")
        self.assertEqual(scan.call_args_list[0].args[0][-1], str(self.document))
        launch.assert_called_once_with(self.document, target_app="com.brave.Browser")

    def test_drive_disappearing_during_scan_never_opens(self):
        def eject(_command, **_kwargs):
            self.document.unlink()
            return subprocess.CompletedProcess([], 0, "volume.pdf: OK\n", "")
        with patch.object(opener.subprocess, "run", side_effect=eject), \
             patch.object(opener, "verify_launch_target") as verify, \
             patch.object(opener, "remove_quarantine") as quarantine, \
             patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaises((OSError, RuntimeError)):
                opener.scan_and_open(self.document, "/scanner")
        verify.assert_not_called()
        quarantine.assert_not_called()
        launch.assert_not_called()

    def test_replaced_external_pdf_with_identical_bytes_never_opens(self):
        original = self.document.read_bytes()
        def replace(_command, **_kwargs):
            self.document.unlink()
            self.document.write_bytes(original)
            return subprocess.CompletedProcess([], 0, "volume.pdf: OK\n", "")
        with patch.object(opener.subprocess, "run", side_effect=replace), \
             patch.object(opener, "verify_launch_target") as verify, \
             patch.object(opener, "remove_quarantine") as quarantine, \
             patch.object(opener, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "changed"):
                opener.scan_and_open(self.document, "/scanner")
        verify.assert_not_called()
        quarantine.assert_not_called()
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
