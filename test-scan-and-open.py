#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True

spec = importlib.util.spec_from_file_location('scan_and_open', Path(__file__).with_name('scan-and-open.py'))
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class ScanGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name).resolve() / 'selected file.PDF'
        self.file.write_bytes(b'%PDF-1.4\nTest document')

    def assert_blocked(self, result=None, exception=None):
        with patch.object(opener.subprocess, 'run', return_value=result, side_effect=exception) as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaises(RuntimeError):
                opener.scan_and_open(str(self.file), '/scanner')
            self.assertEqual(run.call_count, 1)
            remove.assert_not_called()
            self.assertEqual(self.file.read_bytes(), b'%PDF-1.4\nTest document')

    def test_detection_preserves_file_and_quarantine_without_opening(self):
        self.assert_blocked(subprocess.CompletedProcess([], 1, 'test: Eicar-Signature FOUND', ''))

    def test_scan_error_does_not_open(self):
        self.assert_blocked(subprocess.CompletedProcess([], 2, '', 'Cannot read file'))

    def test_timeout_does_not_open(self):
        self.assert_blocked(exception=subprocess.TimeoutExpired('/scanner', 180))

    def test_skipped_file_or_warning_does_not_open(self):
        for stdout, stderr in [('file: Empty file', ''), ('OK-named.pdf: Empty file', ''), ('file: OK', 'WARNING: skipped input')]:
            with self.subTest(stdout=stdout):
                self.assert_blocked(subprocess.CompletedProcess([], 0, stdout, stderr))

    def test_changed_file_does_not_remove_quarantine_or_open(self):
        def scan(*args, **kwargs):
            self.file.write_bytes(b'changed')
            return subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=scan) as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
            self.assertEqual(run.call_count, 1)
            remove.assert_not_called()

    def test_clean_pdf_removes_quarantine_then_opens_in_brave(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine', side_effect=lambda *args: calls.append('remove quarantine')):
            opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(calls[1], 'remove quarantine')
        self.assertEqual(calls[2], ['/usr/bin/open', '-b', 'com.brave.Browser', str(self.file)])
        self.assertIn('--alert-exceeds-max=yes', calls[0])
        self.assertIn('--alert-encrypted=yes', calls[0])

    def test_missing_or_stale_signatures_block_before_scanning(self):
        database = Path(self.temp.name) / 'database'
        database.mkdir()
        stamp = database / 'last-successful-update'
        with patch.object(opener, 'DATABASE', database), patch.object(opener, 'STAMP', stamp):
            with self.assertRaises(RuntimeError):
                opener.check_database()
            stamp.write_text(str(time.time() - 49 * 60 * 60))
            with self.assertRaisesRegex(RuntimeError, '48 hours'):
                opener.check_database()
            stamp.write_text(str(time.time()))
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                opener.check_database()

    def test_large_pdf_has_no_configured_scan_size_limit(self):
        # Simulate an oversized PDF without allocating a large test file.
        completed = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener, 'MAX_FILE_SIZE', 1), \
                patch.object(opener.subprocess, 'run', return_value=completed) as run, \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
        command = run.call_args_list[0].args[0]
        self.assertIn('--max-filesize=0', command)
        self.assertIn('--max-scansize=0', command)
        self.assertIn('--alert-exceeds-max=yes', command)
        self.assertEqual(run.call_args_list[0].kwargs['timeout'], opener.PDF_SCAN_TIMEOUT)
        self.assertEqual(run.call_count, 2)

    def test_pdf_engine_size_limit_still_blocks(self):
        self.assert_blocked(subprocess.CompletedProcess(
            [], 1, 'file: Heuristics.Limits.Exceeded.MaxFileSize FOUND', ''))

    def test_oversized_non_pdf_blocks_before_scanning(self):
        document = self.file.with_suffix('.txt')
        document.write_bytes(self.file.read_bytes())
        with patch.object(opener, 'MAX_FILE_SIZE', 1), patch.object(opener.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, '512 MB'):
                opener.scan_and_open(str(document), '/scanner')
            run.assert_not_called()

    def test_nested_pdf_in_app_bundle_still_has_size_limit(self):
        bundle = Path(self.temp.name) / 'Example.app'
        bundle.mkdir()
        (bundle / 'large.pdf').write_bytes(self.file.read_bytes())
        with patch.object(opener, 'MAX_FILE_SIZE', 1), patch.object(opener.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, '512 MB'):
                opener.scan_and_open(str(bundle), '/scanner')
            run.assert_not_called()

    def test_non_pdf_keeps_existing_clamav_size_limits(self):
        document = self.file.with_suffix('.txt')
        document.write_bytes(self.file.read_bytes())
        completed = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', return_value=completed) as run, \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(document), '/scanner')
        command = run.call_args_list[0].args[0]
        self.assertIn('--max-filesize=512M', command)
        self.assertIn('--max-scansize=1024M', command)
        self.assertEqual(run.call_args_list[0].kwargs['timeout'], 180)

    def test_missing_scanner_blocks_before_modifying_any_file(self):
        with patch.object(opener, 'scanner_path', side_effect=RuntimeError('unavailable')), \
                patch.object(opener, 'scan_and_open') as scan, patch('sys.stderr'):
            self.assertEqual(opener.main([str(self.file)]), 1)
            scan.assert_not_called()


if __name__ == '__main__':
    unittest.main()
