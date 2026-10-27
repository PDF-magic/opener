#!/usr/bin/env python3
"""Verify optional browser download identifiers never affect scan security."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "browser_download_id", Path(__file__).with_name("scan-and-open.py"))
opener = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = opener
spec.loader.exec_module(opener)


class BrowserIdentifierTests(unittest.TestCase):
    def test_plain_paths_do_not_infer_identifier(self):
        requests = opener.parse_scan_requests(["/tmp/a.pdf", "/tmp/b.pdf"])
        self.assertEqual([r.path for r in requests], ["/tmp/a.pdf", "/tmp/b.pdf"])
        self.assertEqual([r.browser_download_identifier for r in requests], [None, None])

    def test_browser_request_is_routed_with_unchanged_path(self):
        request, = opener.parse_scan_requests([
            "--browser-download-id", "download-42", "/tmp/local.pdf"])
        with patch.object(opener, "scanner_path", return_value="/scanner"), \
                patch.object(opener, "check_database"), \
                patch.object(opener, "validate_scan_request"), \
                patch.object(opener, "scan_and_open") as run:
            self.assertEqual(opener.main([request]), 0)
        run.assert_called_once_with("/tmp/local.pdf", "/scanner",
                                    browser_download_identifier="download-42")

    def test_invalid_identifiers_fail_before_processing(self):
        for args in (
            ["--browser-download-id"],
            ["--browser-download-id", "", "/tmp/file.pdf"],
            ["--browser-download-id", "bad\nvalue", "/tmp/file.pdf"],
            ["--browser-download-id", "x" * 257, "/tmp/file.pdf"],
            ["--browser-download-id", "id", "/tmp/a.pdf", "/tmp/b.pdf"],
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                opener.parse_scan_requests(args)

    def test_metadata_is_stored_only_in_immutable_request(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "download.pdf"
            file.write_bytes(b"%PDF-1.4\nTest")
            seen = []
            original = opener.ScanRequest.from_path

            def record(path, **kwargs):
                result = original(path, **kwargs)
                seen.append(result)
                return result

            with patch.object(opener.ScanRequest, "from_path", side_effect=record), \
                    patch.object(opener, "CACHE_DB", Path(folder) / "cache.sqlite3"), \
                    patch.object(opener, "SCAN_REQUEST_DB", Path(folder) / "audit.sqlite3"), \
                    patch.object(opener.subprocess, "run",
                                 return_value=subprocess.CompletedProcess([], 1, "file: Malware FOUND", "")), \
                    patch.object(opener, "remove_quarantine") as quarantine:
                with self.assertRaises(RuntimeError):
                    opener.scan_and_open(str(file), "/scanner",
                                         browser_download_identifier="download-42")
            self.assertEqual(seen[0].browser_download_identifier, "download-42")
            self.assertEqual(seen[0].file_type, "pdf")
            quarantine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
