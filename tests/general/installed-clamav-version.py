#!/usr/bin/env python3
"""Read-only installed ClamAV version detection regression tests."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "scan_and_open", (Path(__file__).resolve().parents[2] / "scan-and-open.py")
)
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class InstalledClamAVVersionTests(unittest.TestCase):
    def test_detects_version_at_an_installed_trusted_path_without_scanning(self):
        # Installed executable discovery now requires an existing regular file
        # before querying its executable permission.
        with patch.object(
            opener.Path, "is_file", autospec=True,
            side_effect=lambda path: str(path) == "/usr/local/bin/clamscan",
        ) as is_file, patch.object(
            opener.os, "access", side_effect=lambda path, mode: path == "/usr/local/bin/clamscan"
        ) as access, patch.object(
            opener.subprocess, "check_output",
            return_value="ClamAV 1.4.2/28765/Mon Oct 28",
        ) as query, patch.object(
            opener, "check_database", side_effect=AssertionError("No database check")
        ), patch.object(
            opener, "run_scan_command", side_effect=AssertionError("No file scan")
        ), patch.object(
            opener, "launch_clean_file", side_effect=AssertionError("No file opening")
        ), patch.object(
            opener, "remember_clean", side_effect=AssertionError("No cache writes")
        ):
            self.assertEqual(opener.detect_installed_clamav_version(), "1.4.2")
        self.assertEqual(is_file.call_count, 2)
        self.assertEqual(access.call_count, 1)
        query.assert_called_once_with(
            ["/usr/local/bin/clamscan", "--version"],
            text=True, timeout=5, stderr=subprocess.DEVNULL,
        )

    def test_absent_scanner_reports_unknown_without_invoking_a_process(self):
        with patch.object(opener.Path, "is_file", return_value=True), patch.object(
            opener.os, "access", return_value=False
        ) as access, patch.object(
            opener.subprocess, "check_output"
        ) as query:
            self.assertIsNone(opener.detect_installed_clamav_version())
        self.assertEqual(access.call_count, 3)
        query.assert_not_called()

    def test_nonfile_candidates_do_not_probe_executable_permissions_or_version(self):
        with patch.object(opener.Path, "is_file", return_value=False), patch.object(
            opener.os, "access"
        ) as access, patch.object(
            opener.subprocess, "check_output"
        ) as query:
            self.assertIsNone(opener.detect_installed_clamav_version())
        access.assert_not_called()
        query.assert_not_called()

    def test_unreadable_or_unrecognized_version_is_unknown(self):
        with patch.object(opener, "detect_clamav_installation", return_value="/trusted/clamscan"), patch.object(
            opener.subprocess, "check_output"
        ) as query:
            query.return_value = "Not ClamAV"
            self.assertIsNone(opener.detect_installed_clamav_version())
            query.side_effect = subprocess.TimeoutExpired("/trusted/clamscan", 5)
            self.assertIsNone(opener.detect_installed_clamav_version())
            query.side_effect = FileNotFoundError()
            self.assertIsNone(opener.detect_installed_clamav_version())

    def test_installed_version_is_not_a_cached_scan_version(self):
        with patch.object(opener, "detect_clamav_installation", return_value="/trusted/clamscan"), patch.object(
            opener.subprocess, "check_output",
            side_effect=["ClamAV 1.4.2/28765", "ClamAV 1.5.0/28766"],
        ) as query, patch.object(
            opener, "cached_scan", side_effect=AssertionError("No cache reads")
        ):
            self.assertEqual(opener.detect_installed_clamav_version(), "1.4.2")
            self.assertEqual(opener.detect_installed_clamav_version(), "1.5.0")
        self.assertEqual(query.call_count, 2)

    def test_discovery_failure_never_reports_an_installed_version(self):
        with patch.object(
            opener, "detect_clamav_installation", side_effect=RuntimeError("ClamAV unavailable")
        ), patch.object(opener, "scan_engine_version") as query:
            self.assertIsNone(opener.detect_installed_clamav_version())
        query.assert_not_called()


if __name__ == "__main__":
    unittest.main()
