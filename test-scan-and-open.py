#!/usr/bin/env python3
import importlib.util
import threading
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

    def run_parallel_scans(self, change_waiter=False, fail_first=False):
        another = self.file.with_name('same-content-different-path.pdf')
        another.write_bytes(self.file.read_bytes())
        first_running = threading.Event()
        waiter_cache_miss = threading.Event()
        release_first = threading.Event()
        outcomes = {}
        calls = []
        command_lock = threading.Lock()
        original_cache_lookup = opener.cached_clean

        def cached_clean(digest):
            hit = original_cache_lookup(digest)
            if threading.current_thread().name == 'waiter' and not hit:
                waiter_cache_miss.set()
            return hit

        def run(command, **kwargs):
            with command_lock:
                calls.append(command)
                scan_number = sum(c[0] == '/scanner' for c in calls)
            if command[0] == '/scanner' and scan_number == 1:
                first_running.set()
                if not release_first.wait(10):
                    raise RuntimeError('Test scanner was not released')
                if fail_first:
                    return subprocess.CompletedProcess(command, 1, 'file: Malware FOUND', '')
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')

        def worker(path):
            try:
                opener.scan_and_open(str(path), '/scanner')
                outcomes[threading.current_thread().name] = 'opened'
            except (OSError, RuntimeError) as error:
                outcomes[threading.current_thread().name] = str(error)

        with patch.object(opener, 'cached_clean', side_effect=cached_clean), \
                patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine'):
            first = threading.Thread(target=worker, args=(self.file,), name='first')
            waiter = threading.Thread(target=worker, args=(another,), name='waiter')
            try:
                first.start()
                self.assertTrue(first_running.wait(10), 'Initial scan never started')
                waiter.start()
                self.assertTrue(waiter_cache_miss.wait(10), 'Waiter never saw a cache miss')
                if change_waiter:
                    another.write_bytes(b'%PDF-1.4\\nchanged while waiting')
            finally:
                release_first.set()
                if first.ident is not None:
                    first.join(timeout=10)
                if waiter.ident is not None:
                    waiter.join(timeout=10)
        self.assertFalse(first.is_alive(), 'First scan did not terminate')
        self.assertFalse(waiter.is_alive(), 'Waiting scan did not terminate')
        return outcomes, [call[0] for call in calls]

    def test_identical_content_concurrent_requests_share_only_one_scan(self):
        outcomes, calls = self.run_parallel_scans()
        self.assertEqual(outcomes, {'first': 'opened', 'waiter': 'opened'})
        self.assertEqual(calls.count('/scanner'), 1)
        self.assertEqual(calls.count('/usr/bin/open'), 2)

    def test_waiter_detects_file_changed_while_another_scan_runs(self):
        outcomes, calls = self.run_parallel_scans(change_waiter=True)
        self.assertEqual(outcomes.get('first'), 'opened')
        self.assertIn('changed', outcomes.get('waiter', ''))
        self.assertEqual(calls.count('/scanner'), 1)
        self.assertEqual(calls.count('/usr/bin/open'), 1)

    def test_infected_active_scan_does_not_supply_reusable_verdict(self):
        outcomes, calls = self.run_parallel_scans(fail_first=True)
        self.assertIn('Malware', outcomes.get('first', ''))
        self.assertEqual(outcomes.get('waiter'), 'opened')
        self.assertEqual(calls.count('/scanner'), 2)
        self.assertEqual(calls.count('/usr/bin/open'), 1)

    def test_failed_lock_acquisition_fails_closed(self):
        with patch.object(opener, 'active_scan_lock', side_effect=OSError('lock denied')), \
                patch.object(opener.subprocess, 'run') as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaises(OSError):
                opener.scan_and_open(str(self.file), '/scanner')
            run.assert_not_called()
            remove.assert_not_called()

    def test_active_scan_lock_applies_across_processes(self):
        marker = Path(self.temp.name) / 'acquired'
        child = """import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location('scan_gate', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.CACHE_DB = pathlib.Path(sys.argv[2])
print('ready', flush=True)
with module.active_scan_lock(bytes.fromhex(sys.argv[3])):
    pathlib.Path(sys.argv[4]).write_text('acquired')
"""
        digest = opener.cache_key(opener.fingerprint(self.file), True)
        with opener.active_scan_lock(digest):
            process = subprocess.Popen(
                [sys.executable, '-c', child, str(Path(__file__).with_name('scan-and-open.py')),
                 str(opener.CACHE_DB), digest.hex(), str(marker)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
                self.assertFalse(marker.exists())
                self.assertIsNone(process.poll(), 'Child must block on active scan lock')
            except BaseException:
                process.kill()
                process.communicate(timeout=5)
                raise
        stdout, stderr = process.communicate(timeout=10)
        self.assertEqual(process.returncode, 0, stderr)
        self.assertTrue(marker.exists())

    def test_valid_requests_accept_files_apps_and_file_aliases(self):
        bundle = Path(self.temp.name) / 'Example.app'
        bundle.mkdir()
        alias = Path(self.temp.name) / 'selected alias.pdf'
        alias.symlink_to(self.file)
        for selection, expected in (
                (str(self.file), self.file),
                (self.file, self.file),
                (str(bundle), bundle),
                (str(alias), self.file)):
            with self.subTest(selection=selection):
                self.assertEqual(opener.validate_scan_request(selection), expected)

    def test_invalid_requests_stop_before_any_scan_side_effects(self):
        broken = Path(self.temp.name) / 'broken.pdf'
        broken.symlink_to(Path(self.temp.name) / 'missing.pdf')
        invalid = (
            '', None, b'bytes.pdf', 'bad\0path.pdf',
            Path(self.temp.name), Path(self.temp.name) / 'missing.pdf',
            broken,
        )
        with patch.object(opener, 'fingerprint') as fingerprint, \
                patch.object(opener, 'cached_clean') as cache, \
                patch.object(opener.subprocess, 'run') as run, \
                patch.object(opener, 'remove_quarantine') as quarantine:
            for selection in invalid:
                with self.subTest(selection=repr(selection)):
                    with self.assertRaises((OSError, RuntimeError)):
                        opener.scan_and_open(selection, '/scanner')
            fingerprint.assert_not_called()
            cache.assert_not_called()
            run.assert_not_called()
            quarantine.assert_not_called()

    def test_empty_request_batch_is_an_error_without_scanner_setup(self):
        with patch.object(opener, 'scanner_path') as scanner, \
                patch.object(opener, 'check_database') as signatures, \
                patch.object(opener, 'scan_and_open') as scan, patch('sys.stderr'):
            self.assertEqual(opener.main([]), 1)
            scanner.assert_not_called()
            signatures.assert_not_called()
            scan.assert_not_called()

    def test_invalid_batch_items_do_not_initialize_scanner(self):
        with patch.object(opener, 'scanner_path') as scanner, \
                patch.object(opener, 'check_database') as signatures, \
                patch.object(opener, 'scan_and_open') as scan, patch('sys.stderr'):
            self.assertEqual(opener.main(['', str(self.file.with_name('missing.pdf'))]), 1)
            scanner.assert_not_called()
            signatures.assert_not_called()
            scan.assert_not_called()

    def test_batch_checks_each_request_and_processes_only_valid_ones(self):
        with patch.object(opener, 'scanner_path', return_value='/scanner'), \
                patch.object(opener, 'check_database'), \
                patch.object(opener, 'scan_and_open') as scan, patch('sys.stderr'):
            self.assertEqual(opener.main(['', str(self.file), str(self.file.with_name('missing.pdf'))]), 1)
            scan.assert_called_once_with(str(self.file), '/scanner')

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

    def test_pdf_cache_uses_separate_scan_policy(self):
        document = self.file.with_suffix('.txt')
        document.write_bytes(self.file.read_bytes())
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(document), '/scanner')
            opener.scan_and_open(str(self.file), '/scanner')
            opener.scan_and_open(str(self.file), '/scanner')
        scans = [command for command in calls if command[0] == '/scanner']
        self.assertEqual(len(scans), 2)
        self.assertIn('--max-filesize=512M', scans[0])
        self.assertIn('--max-filesize=0', scans[1])

    def test_existing_non_pdf_cache_key_is_preserved(self):
        document = self.file.with_suffix('.txt')
        document.write_bytes(self.file.read_bytes())
        opener.remember_clean(opener.fingerprint(document))
        with patch.object(opener.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'file: OK', '')) as run, \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(document), '/scanner')
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], '/usr/bin/open')

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
