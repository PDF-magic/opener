#!/usr/bin/env python3
"""Bounded scanner slots: overlapping requests, queueing, and process isolation."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
source = Path(__file__).with_name('scan-and-open.py')
spec = importlib.util.spec_from_file_location('scan_and_open', source)
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class ScanConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        setting = patch.object(opener, 'CACHE_DB', Path(self.temp.name) / 'clean-cache.sqlite3')
        setting.start()
        self.addCleanup(setting.stop)

    def test_different_documents_overlap_but_excess_requests_queue(self):
        mutex = threading.Lock()
        active = 0
        peak = 0
        seen = []

        def fake_scan(item, _scanner):
            nonlocal active, peak
            with mutex:
                active += 1
                peak = max(peak, active)
                seen.append(item)
            time.sleep(0.12)
            with mutex:
                active -= 1

        with patch.object(opener, '_scan_and_open', side_effect=fake_scan):
            with ThreadPoolExecutor(max_workers=5) as pool:
                list(pool.map(lambda item: opener.scan_and_open(item, '/scanner'),
                              ('a.pdf', 'b.pdf', 'c.pdf', 'd.pdf', 'e.pdf')))
        self.assertEqual(peak, opener.MAX_CONCURRENT_SCANS)
        self.assertEqual(active, 0)
        self.assertCountEqual(seen, ('a.pdf', 'b.pdf', 'c.pdf', 'd.pdf', 'e.pdf'))

    def test_waiting_request_starts_when_slot_is_released(self):
        started = threading.Event()
        acquired = threading.Event()

        def waiter():
            started.set()
            with opener.scan_slot():
                acquired.set()

        with opener.scan_slot():
            with opener.scan_slot():
                thread = threading.Thread(target=waiter)
                thread.start()
                self.assertTrue(started.wait(2))
                self.assertFalse(acquired.wait(0.15), 'Third scan bypassed the queue')
            self.assertTrue(acquired.wait(2), 'Queued scan did not resume')
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())

    def test_slot_is_released_when_scan_fails(self):
        with patch.object(opener, '_scan_and_open', side_effect=RuntimeError('scan failed')):
            with self.assertRaisesRegex(RuntimeError, 'scan failed'):
                opener.scan_and_open('first.pdf', '/scanner')
        with patch.object(opener, '_scan_and_open', return_value='ok'):
            self.assertEqual(opener.scan_and_open('second.pdf', '/scanner'), 'ok')

    def test_locks_limit_independent_processes(self):
        child_code = """
import importlib.util
from pathlib import Path
import sys
spec = importlib.util.spec_from_file_location('scan_and_open', sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.CACHE_DB = Path(sys.argv[2]) / 'clean-cache.sqlite3'
with mod.scan_slot():
    print('acquired', flush=True)
"""
        with opener.scan_slot():
            with opener.scan_slot():
                child = subprocess.Popen(
                    [sys.executable, '-c', child_code, str(source), self.temp.name],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                self.addCleanup(lambda: child.kill() if child.poll() is None else None)
                time.sleep(0.2)
                self.assertIsNone(child.poll(), 'External scan bypassed the shared limit')
            stdout, stderr = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, stderr)
        self.assertEqual(stdout.strip(), 'acquired')

    def test_native_and_python_limits_agree(self):
        swift = Path(__file__).with_name('brave-pdf-opener.swift').read_text()
        self.assertIn(f'private let maxConcurrentScans = {opener.MAX_CONCURRENT_SCANS}', swift)


if __name__ == '__main__':
    unittest.main()
