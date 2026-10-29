#!/usr/bin/env python3
"""Reject unsupported ClamAV versions before a PDF or cached result can open."""
import importlib.util
import io
from contextlib import redirect_stderr
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

SCANNER = "/opt/homebrew/bin/clamscan"
UNSUPPORTED = "Unsupported ClamAV scanner version."
UNVERIFIED = "ClamAV scanner version could not be verified."


class ClamAVVersionSupportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="clamav-version-check-")
        self.addCleanup(temporary.cleanup)
        self.pdf = Path(temporary.name) / "private example.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nexample\n")
        # Installation discovery requires a regular executable file.
        file_check = patch.object(opener.Path, "is_file", return_value=True)
        file_check.start()
        self.addCleanup(file_check.stop)
        executable = patch.object(opener.os, "access",
                                  side_effect=lambda path, mode: path == SCANNER)
        executable.start()
        self.addCleanup(executable.stop)

    def test_supported_releases_preserve_engine_selection(self):
        for version in ("1.4.0", "1.4.6", "1.5.0", "1.5.4"):
            with self.subTest(version=version):
                with patch.object(opener.subprocess, "check_output",
                                  return_value=f"ClamAV {version}/27800/Mon Oct 26") as read:
                    self.assertEqual(opener.scanner_path(), SCANNER)
                read.assert_called_once_with(
                    [SCANNER, "--version"], text=True, timeout=5,
                    stderr=subprocess.DEVNULL)

    def test_advisory_installation_and_version_discovery_remain_read_only(self):
        # The separate detection tasks do not become enforced scan admission.
        with patch.object(opener.subprocess, "check_output",
                          return_value="ClamAV 1.3.2/27800") as query:
            self.assertEqual(opener.detect_clamav_installation(), SCANNER)
            self.assertEqual(opener.detect_installed_clamav_version(), "1.3.2")
        query.assert_called_once()

    def test_unsupported_releases_never_select_a_scanner(self):
        for version in ("0.103.12", "1.0.9", "1.3.2", "1.6.0", "2.0.0"):
            with self.subTest(version=version):
                with patch.object(opener.subprocess, "check_output",
                                  return_value=f"ClamAV {version}/27800"):
                    with self.assertRaisesRegex(RuntimeError, UNSUPPORTED):
                        opener.scanner_path()

    def test_unverifiable_versions_fail_closed_without_exposing_raw_output(self):
        cases = (subprocess.TimeoutExpired([SCANNER, "--version"], 5),
                 FileNotFoundError("private executable path"),
                 subprocess.CalledProcessError(1, [SCANNER, "--version"]),
                 UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
                 "not ClamAV; /private/secret", "ClamAV 1.5", "",
                 "ClamAV 1.4.6-rc1/27800",
                 "ClamAV 1.5.4+unreviewed/27800", "ClamAV 1.5.4.1/27800")
        for response in cases:
            with self.subTest(response=repr(response)):
                with patch.object(opener.subprocess, "check_output") as read:
                    if isinstance(response, BaseException):
                        read.side_effect = response
                    else:
                        read.return_value = response
                    with self.assertRaisesRegex(RuntimeError, UNVERIFIED) as error:
                        opener.scanner_path()
                self.assertNotIn("private", str(error.exception))
                self.assertNotIn(SCANNER, str(error.exception))

    def test_unsupported_first_candidate_is_not_bypassed_by_later_binary(self):
        with patch.object(opener.os, "access", return_value=True), \
                patch.object(opener.subprocess, "check_output",
                             return_value="ClamAV 1.3.2/27800") as read:
            with self.assertRaisesRegex(RuntimeError, UNSUPPORTED):
                opener.scanner_path()
        self.assertEqual(read.call_count, 1)

    def test_unsupported_version_stops_main_before_scan_cache_and_handoff(self):
        with patch.object(opener.subprocess, "check_output",
                          return_value="ClamAV 1.3.2/27800"), \
                patch.object(opener, "watch_parent_lifetime"), \
                patch.object(opener, "check_database") as database, \
                patch.object(opener, "scan_and_open") as scan, \
                patch.object(opener, "cached_scan") as cache, \
                patch.object(opener, "remove_quarantine") as quarantine, \
                patch.object(opener, "launch_clean_file") as launch, \
                redirect_stderr(io.StringIO()) as output:
            self.assertEqual(opener.main([str(self.pdf)]), 1)
        self.assertIn(UNSUPPORTED, output.getvalue())
        self.assertNotIn(str(self.pdf), output.getvalue())
        database.assert_not_called()
        cache.assert_not_called()
        scan.assert_not_called()
        quarantine.assert_not_called()
        launch.assert_not_called()

    def test_supported_version_retains_the_existing_scan_and_database_gates(self):
        with patch.object(opener.subprocess, "check_output",
                          return_value="ClamAV 1.5.4/27800"), \
                patch.object(opener, "watch_parent_lifetime"), \
                patch.object(opener, "check_database") as database, \
                patch.object(opener, "scan_and_open") as scan, \
                patch.object(opener, "record_scan_request") as record, \
                redirect_stderr(io.StringIO()):
            self.assertEqual(opener.main([str(self.pdf)]), 0)
        database.assert_called_once_with()
        record.assert_called_once_with("Command Line")
        scan.assert_called_once_with(str(self.pdf), SCANNER)


if __name__ == "__main__":
    unittest.main()
