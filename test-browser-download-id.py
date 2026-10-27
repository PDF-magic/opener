#!/usr/bin/env python3
"""Verify that browser download metadata is optional and cannot bypass scanning."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    'scan_and_open', Path(__file__).with_name('scan-and-open.py'))
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class BrowserDownloadIdentifierTests(unittest.TestCase):
    def test_regular_file_requests_have_no_browser_identifier(self):
        requests = opener.parse_scan_requests(['/tmp/first.pdf', '/tmp/second.pdf'])
        self.assertEqual([request.path for request in requests],
                         ['/tmp/first.pdf', '/tmp/second.pdf'])
        self.assertTrue(all(request.browser_download_identifier is None
                            for request in requests))

    def test_explicit_browser_identifier_is_kept_with_its_request(self):
        requests = opener.parse_scan_requests([
            '--browser-download-id', 'download-0042', '/tmp/download.pdf'])
        self.assertEqual(len(requests), 1)
        with patch.object(opener, 'scanner_path', return_value='/scanner'), \
                patch.object(opener, 'check_database'), \
                patch.object(opener, 'scan_and_open') as scan:
            self.assertEqual(opener.main(requests), 0)
        request, scanner = scan.call_args.args
        self.assertEqual(request.path, '/tmp/download.pdf')
        self.assertEqual(request.browser_download_identifier, 'download-0042')
        self.assertEqual(scanner, '/scanner')

    def test_missing_or_invalid_identifier_is_rejected(self):
        for args in (
            ['--browser-download-id'],
            ['--browser-download-id', '', '/tmp/file.pdf'],
            ['--browser-download-id', 'bad\nvalue', '/tmp/file.pdf'],
            ['--browser-download-id', 'a' * 257, '/tmp/file.pdf'],
            ['--browser-download-id', 'id', '/tmp/a.pdf', '/tmp/b.pdf'],
        ):
            with self.subTest(args=args), self.assertRaises(ValueError):
                opener.parse_scan_requests(args)

    def test_identifier_never_skips_scan_or_changes_open_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'download.pdf'
            path.write_bytes(b'%PDF-1.4\nTest')
            request = opener.ScanRequest(str(path), 'download-0042')
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, 'file: OK', '')
            with patch.object(opener, 'CACHE_DB', Path(directory) / 'cache.sqlite3'), \
                    patch.object(opener.subprocess, 'run', side_effect=run), \
                    patch.object(opener, 'remove_quarantine') as quarantine:
                opener.scan_and_open(request, '/scanner')
            self.assertEqual(calls[0][0], '/scanner')
            self.assertEqual(calls[0][-1], str(path))
            self.assertIn('--alert-encrypted=yes', calls[0])
            self.assertEqual(calls[1], [
                '/usr/bin/open', '-b', 'com.brave.Browser', str(path)])
            quarantine.assert_called_once_with(path)


if __name__ == '__main__':
    unittest.main()
