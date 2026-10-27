#!/usr/bin/env python3
import importlib.util
import os
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
        cache = patch.object(opener, 'CACHE_DB', Path(self.temp.name) / 'clean-cache.sqlite3')
        cache.start()
        self.addCleanup(cache.stop)

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

    def test_oversized_file_blocks_before_scanning(self):
        with patch.object(opener, 'MAX_FILE_SIZE', 1), patch.object(opener.subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, '512 MB'):
                opener.scan_and_open(str(self.file), '/scanner')
            run.assert_not_called()

    def test_missing_scanner_blocks_before_modifying_any_file(self):
        with patch.object(opener, 'scanner_path', side_effect=RuntimeError('unavailable')), \
                patch.object(opener, 'scan_and_open') as scan, patch('sys.stderr'):
            self.assertEqual(opener.main([str(self.file)]), 1)
            scan.assert_not_called()


    def test_cached_clean_scan_reuses_identical_file_after_rename(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
            renamed = self.file.with_name('renamed.pdf')
            self.file.rename(renamed)
            opener.scan_and_open(str(renamed), '/scanner')
        self.assertEqual(sum(cmd[0] == '/scanner' for cmd in calls), 1)
        self.assertEqual(sum(cmd[0] == '/usr/bin/open' for cmd in calls), 2)

    def test_file_timestamps_are_not_cache_keys(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
            os.utime(self.file, None)
            opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(sum(cmd[0] == '/scanner' for cmd in calls), 1)

    def test_changed_bytes_with_preserved_mtime_force_new_scan(self):
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
            old = self.file.stat()
            self.file.write_bytes(b'%PDF-1.4\nEvil document')
            os.utime(self.file, ns=(old.st_atime_ns, old.st_mtime_ns))
            opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(sum(cmd[0] == '/scanner' for cmd in calls), 2)

    def test_clean_cache_expires_after_90_days_without_sliding(self):
        scans = []
        def run(command, **kwargs):
            if command[0] == '/scanner':
                scans.append(command)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        initial = 1800000000
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine'):
            with patch.object(opener.time, 'time', return_value=initial):
                opener.scan_and_open(str(self.file), '/scanner')
            with patch.object(opener.time, 'time', return_value=initial + opener.CACHE_TTL - 1):
                opener.scan_and_open(str(self.file), '/scanner')
            with patch.object(opener.time, 'time', return_value=initial + opener.CACHE_TTL):
                opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(len(scans), 2)

    def test_invalid_cache_causes_rescan_not_bypass(self):
        opener.CACHE_DB.write_text('not an SQLite database')
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
            opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(sum(cmd[0] == '/scanner' for cmd in calls), 2)

    def test_infected_scan_is_not_cached(self):
        scan = subprocess.CompletedProcess([], 1, 'file: Malware FOUND', '')
        with patch.object(opener.subprocess, 'run', return_value=scan) as run, \
                patch.object(opener, 'remove_quarantine') as quarantine:
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, 'Malware'):
                    opener.scan_and_open(str(self.file), '/scanner')
            self.assertEqual(run.call_count, 2)
            quarantine.assert_not_called()

    def test_cached_file_changing_during_rehash_still_blocks(self):
        scan = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', return_value=scan), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
        original = opener.fingerprint
        counts = [0]
        def fingerprint(path):
            counts[0] += 1
            if counts[0] == 2:
                self.file.write_bytes(b'changed while being opened')
            return original(path)
        with patch.object(opener, 'fingerprint', side_effect=fingerprint), \
                patch.object(opener.subprocess, 'run') as run, \
                patch.object(opener, 'remove_quarantine') as quarantine:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
            run.assert_not_called()
            quarantine.assert_not_called()

    def test_invalid_signatures_still_block_caching(self):
        scan = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', return_value=scan), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
        with patch.object(opener, 'scanner_path', return_value='/scanner'), \
                patch.object(opener, 'check_database', side_effect=RuntimeError('stale')), \
                patch.object(opener.subprocess, 'run') as run, patch('sys.stderr'):
            self.assertEqual(opener.main([str(self.file)]), 1)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
