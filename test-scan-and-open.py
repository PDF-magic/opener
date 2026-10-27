#!/usr/bin/env python3
import importlib.util
import io
from dataclasses import FrozenInstanceError, replace
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

    def test_scan_request_records_normalized_file_type(self):
        cases = (
            (self.file, 'pdf'),
            (self.file.with_suffix('.txt'), 'txt'),
            (self.file.with_name('archive.tar.gz'), 'gz'),
            (self.file.with_name('extensionless'), 'unknown'),
            (self.file.with_name('Example.app'), 'app'),
        )
        for path, expected in cases:
            with self.subTest(path=path):
                request = opener.ScanRequest.from_path(path)
                self.assertEqual(request.file_type, expected)


    def test_scan_request_has_optional_cancellation_field(self):
        request = opener.ScanRequest.from_path(self.file)
        self.assertIs(request.cancellation_requested, False)
        cancelled_request = replace(request, cancellation_requested=True)
        self.assertIs(cancelled_request.cancellation_requested, True)
        self.assertIs(request.cancellation_requested, False)
        self.assertEqual(cancelled_request.file_type, request.file_type)

    def test_source_url_is_optional_request_metadata(self):
        local = opener.ScanRequest.from_path(self.file)
        origin = 'https://example.test/downloads/report.pdf?version=2'
        sourced = opener.ScanRequest.from_path(self.file, source_url=origin)
        self.assertIsNone(local.source_url)
        self.assertEqual(sourced.source_url, origin)
        self.assertEqual(sourced.file_type, local.file_type)
        self.assertEqual(sourced.file_type, 'pdf')

    def test_source_url_is_recorded_but_not_used_as_scan_target(self):
        origin = 'https://example.test/downloads/report.pdf?version=2'
        requests = []
        from_path = opener.ScanRequest.from_path

        def capture(path, source_url=None):
            request = from_path(path, source_url=source_url)
            requests.append(request)
            return request

        clean = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.ScanRequest, 'from_path', side_effect=capture), \
                patch.object(opener.subprocess, 'run', return_value=clean) as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            opener.scan_and_open(str(self.file), '/scanner', source_url=origin)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].source_url, origin)
        self.assertEqual(run.call_count, 2)
        scan_command = run.call_args_list[0].args[0]
        self.assertEqual(scan_command[-1], str(self.file))
        self.assertNotIn(origin, repr(run.call_args_list))
        self.assertEqual(run.call_args_list[1].args[0][-1], str(self.file))
        remove.assert_called_once_with(self.file)

    def test_source_url_cannot_override_infected_scan(self):
        infected = subprocess.CompletedProcess([], 1, 'file: Malware FOUND', '')
        with patch.object(opener.subprocess, 'run', return_value=infected) as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaisesRegex(RuntimeError, 'Malware'):
                opener.scan_and_open(str(self.file), '/scanner',
                                     source_url='https://example.test/clean.pdf')
        self.assertEqual(run.call_count, 1)
        remove.assert_not_called()

    def test_scan_records_file_type_before_failed_scan(self):
        infected = subprocess.CompletedProcess([], 1, 'file: Malware FOUND', '')
        with patch.object(opener.ScanRequest, 'from_path', wraps=opener.ScanRequest.from_path) as record, \
                patch.object(opener.subprocess, 'run', return_value=infected), \
                patch.object(opener, 'remove_quarantine') as quarantine:
            with self.assertRaisesRegex(RuntimeError, 'Malware'):
                opener.scan_and_open(str(self.file), '/scanner')
        record.assert_called_once_with(self.file, source_url=None)
        quarantine.assert_not_called()

    def test_scan_request_preserves_selected_protection_level(self):
        selected = 'custom-protection-profile'
        request = opener.ScanRequest.from_path(self.file, protection_level=selected)
        self.assertEqual(request.file_type, 'pdf')
        self.assertEqual(request.protection_level, selected)
        self.assertIsNone(opener.ScanRequest.from_path(self.file).protection_level)
        with self.assertRaises(FrozenInstanceError):
            request.protection_level = 'another-profile'

    def test_selected_protection_level_is_recorded_before_scanning(self):
        selected = 'custom-protection-profile'
        completed = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.ScanRequest, 'from_path', wraps=opener.ScanRequest.from_path) as record, \
                patch.object(opener.subprocess, 'run', return_value=completed) as run, \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner', protection_level=selected)
        record.assert_called_once_with(self.file, source_url=None, protection_level=selected)
        self.assertEqual(run.call_count, 2)
        scan_command = run.call_args_list[0].args[0]
        self.assertIn('--max-filesize=0', scan_command)
        self.assertIn('--max-scansize=0', scan_command)
        self.assertIn('--alert-exceeds-max=yes', scan_command)

    def test_selected_protection_level_never_overrides_malware_block(self):
        selected = 'custom-protection-profile'
        detected = subprocess.CompletedProcess([], 1, 'file: Malware FOUND', '')
        with patch.object(opener.ScanRequest, 'from_path', wraps=opener.ScanRequest.from_path) as record, \
                patch.object(opener.subprocess, 'run', return_value=detected) as run, \
                patch.object(opener, 'remove_quarantine') as quarantine:
            with self.assertRaisesRegex(RuntimeError, 'Malware'):
                opener.scan_and_open(str(self.file), '/scanner', protection_level=selected)
        record.assert_called_once_with(self.file, source_url=None, protection_level=selected)
        self.assertEqual(run.call_count, 1)
        quarantine.assert_not_called()

    def test_scanner_failures_do_not_expose_source_details(self):
        private = str(self.file)
        marker = 'PRIVATE_SOURCE_DETAIL'
        cases = (
            subprocess.CompletedProcess([], 1, f'{private}: {marker} FOUND', ''),
            subprocess.CompletedProcess([], 2, '', f'Cannot scan {private}: {marker}'),
            subprocess.CompletedProcess([], 0, f'{private}: OK', f'Warning: {marker}'),
            subprocess.CompletedProcess([], 0, f'{private}: {marker} skipped', ''),
        )
        for completed in cases:
            with self.subTest(returncode=completed.returncode, stdout=completed.stdout):
                with patch.object(opener.subprocess, 'run', return_value=completed), \
                        patch.object(opener, 'remove_quarantine') as quarantine:
                    with self.assertRaises(RuntimeError) as failure:
                        opener.scan_and_open(str(self.file), '/scanner')
                self.assertNotIn(private, str(failure.exception))
                self.assertNotIn(self.file.name, str(failure.exception))
                self.assertNotIn(marker, str(failure.exception))
                quarantine.assert_not_called()

    def test_request_diagnostics_redact_filenames_and_untrusted_exceptions(self):
        errors = (
            RuntimeError('The file changed while checking it; opening was stopped. Try again.'),
            RuntimeError(f'Secret value from {self.file}'),
            OSError(f'Permission denied: {self.file}'),
            subprocess.CalledProcessError(1, ['/usr/bin/open', str(self.file)]),
        )
        output = io.StringIO()
        with patch.object(opener, 'scanner_path', return_value='/scanner'), \
                patch.object(opener, 'check_database'), \
                patch.object(opener, 'scan_and_open', side_effect=errors) as scan, \
                patch('sys.stderr', output):
            self.assertEqual(opener.main([str(self.file)] * len(errors)), 1)
        self.assertEqual(scan.call_count, len(errors))
        diagnostics = output.getvalue()
        self.assertIn('Scan request 1: The file changed', diagnostics)
        self.assertEqual(diagnostics.count('The request could not be processed'), 3)
        self.assertIn('Scan request 4:', diagnostics)
        self.assertNotIn(str(self.file), diagnostics)
        self.assertNotIn(self.file.name, diagnostics)
        self.assertNotIn('Secret value', diagnostics)

    def test_clean_cache_never_persists_source_name_or_path(self):
        completed = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', return_value=completed), \
                patch.object(opener, 'remove_quarantine'):
            opener.scan_and_open(str(self.file), '/scanner')
        data = opener.CACHE_DB.read_bytes()
        self.assertIn(b'clean_scans', data)
        self.assertNotIn(os.fsencode(str(self.file)), data)
        self.assertNotIn(os.fsencode(self.file.name), data)

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

    def test_byte_identical_replacement_during_scan_is_blocked(self):
        original = self.file.read_bytes()
        def scan(command, **kwargs):
            saved = self.file.with_suffix('.backup')
            self.file.rename(saved)
            self.file.write_bytes(original)
            return subprocess.CompletedProcess(command, 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=scan) as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(run.call_count, 1)
        remove.assert_not_called()
        self.assertEqual(self.file.read_bytes(), original)

    def test_change_during_quarantine_removal_blocks_opening(self):
        def remove(path):
            self.file.write_bytes(b'%PDF-1.4\\nChanged after scan')
        completed = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', return_value=completed) as run, \
                patch.object(opener, 'remove_quarantine', side_effect=remove):
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], '/scanner')

    def test_cached_file_changed_during_quarantine_is_not_opened(self):
        digest = opener.cache_key(opener.fingerprint(self.file), True)
        opener.remember_clean(digest)
        def remove(path):
            self.file.write_bytes(b'%PDF-1.4\\nChanged on cache hit')
        with patch.object(opener.subprocess, 'run') as run, \
                patch.object(opener, 'remove_quarantine', side_effect=remove):
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
        run.assert_not_called()

    def test_bundle_member_replaced_with_identical_bytes_is_blocked(self):
        bundle = Path(self.temp.name) / 'Example.app'
        bundle.mkdir()
        nested = bundle / 'Contents'
        nested.mkdir()
        member = nested / 'payload.txt'
        member.write_bytes(b'original bytes')
        def scan(command, **kwargs):
            member.rename(nested / 'old-payload.txt')
            member.write_bytes(b'original bytes')
            (nested / 'old-payload.txt').unlink()
            return subprocess.CompletedProcess(command, 0, str(bundle) + ': OK', '')
        with patch.object(opener.subprocess, 'run', side_effect=scan) as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(bundle), '/scanner')
        self.assertEqual(run.call_count, 1)
        remove.assert_not_called()

    def test_quarantine_metadata_only_change_preserves_clean_open(self):
        contents = self.file.read_bytes()
        def remove(path):
            old = self.file.stat()
            # Removing quarantine can change ctime without changing bytes.
            os.utime(self.file, ns=(old.st_atime_ns, old.st_mtime_ns))
        completed = subprocess.CompletedProcess([], 0, 'file: OK', '')
        with patch.object(opener.subprocess, 'run', return_value=completed) as run, \
                patch.object(opener, 'remove_quarantine', side_effect=remove):
            opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[-1].args[0][0], '/usr/bin/open')
        self.assertEqual(self.file.read_bytes(), contents)

    def test_byte_identical_replacement_during_initial_hash_is_blocked(self):
        original_fingerprint = opener.fingerprint
        def changed_during_fingerprint(path):
            result = original_fingerprint(path)
            saved = self.file.with_suffix('.backup')
            self.file.rename(saved)
            self.file.write_bytes(saved.read_bytes())
            return result
        with patch.object(opener, 'fingerprint', side_effect=changed_during_fingerprint), \
                patch.object(opener.subprocess, 'run') as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
        run.assert_not_called()
        remove.assert_not_called()

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
