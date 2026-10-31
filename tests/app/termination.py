#!/usr/bin/env python3
"""Exercise native owner loss with an actual child scanner and lifetime pipe."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest


class TerminationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.document = self.root / 'document.pdf'
        self.document.write_bytes(b'%PDF-1.4\ntest document')
        self.scanner = self.root / 'fake-clamscan'
        self.started = self.root / 'scan-started'
        self.stopped = self.root / 'scan-stopped'
        self.opened = self.root / 'opened'
        self.unquarantined = self.root / 'unquarantined'
        self.cached = self.root / 'clean-cached'
        self.cache_db = self.root / 'scan-cache.sqlite3'
        self.scanner.write_text(
            '#!' + sys.executable + '\n'
            'import os, signal, sys, time\n'
            'from pathlib import Path\n'
            'def stop(signum, frame):\n'
            '    Path(' + repr(str(self.stopped)) + ').write_text("stopped")\n'
            '    sys.exit(128 + signum)\n'
            'signal.signal(signal.SIGTERM, stop)\n'
            'Path(' + repr(str(self.started)) + ').write_text("started")\n'
            'time.sleep(float(os.environ.get("TEST_SCAN_SLEEP", "30")))\n'
            'print("fake.pdf: OK")\n'
        )
        self.scanner.chmod(0o700)

    def launch(self, sleep='30'):
        scanner_file = str((Path(__file__).resolve().parents[2] / 'scan-and-open.py'))
        harness = (
            'import importlib.util, pathlib, subprocess, sys\n'
            'spec = importlib.util.spec_from_file_location("opener", ' + repr(scanner_file) + ')\n'
            'o = importlib.util.module_from_spec(spec)\n'
            'spec.loader.exec_module(o)\n'
            'o.CACHE_DB = pathlib.Path(' + repr(str(self.cache_db)) + ')\n'
            'o.SCAN_REQUEST_DB = pathlib.Path(' + repr(str(self.root / 'audit.sqlite3')) + ')\n'
            'o.remember_clean = lambda *args: pathlib.Path(' + repr(str(self.cached)) + ').write_text("cached")\n'
            'o.remove_quarantine = lambda path: pathlib.Path(' + repr(str(self.unquarantined)) + ').write_text("removed")\n'
            'o.verify_launch_target = lambda path, target_app=None: None\n'
            'original_run = subprocess.run\n'
            'def safe_run(command, **kwargs):\n'
            '    if command[0] == "/usr/bin/open" or str(command[0]).endswith("/launch-scanned-file"):\n'
            '        pathlib.Path(' + repr(str(self.opened)) + ').write_text("opened")\n'
            '        return subprocess.CompletedProcess(command, 0)\n'
            '    return original_run(command, **kwargs)\n'
            'o.subprocess.run = safe_run\n'
            'o.watch_parent_lifetime()\n'
            'o.scan_and_open(' + repr(str(self.document)) + ', ' + repr(str(self.scanner))
            + ')\n'
        )
        env = dict(os.environ, PDF_MAGIC_PARENT_LIFETIME='1', PDF_MAGIC_NATIVE_CANCEL='1', TEST_SCAN_SLEEP=sleep)
        return subprocess.Popen(
            [sys.executable, '-c', harness], stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)

    def wait_for_start(self, process):
        deadline = time.monotonic() + 5
        while not self.started.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue(self.started.exists(), 'Fake ClamAV never started: ' +
                        (process.stderr.read().decode() if process.poll() is not None else 'process still running'))

    def test_parent_exit_aborts_scan_without_opening_or_cache_write(self):
        child = self.launch()
        try:
            self.wait_for_start(child)
            child.stdin.close()
            self.assertNotEqual(child.wait(timeout=8), 0, 'Abandoned scan reported success')
            deadline = time.monotonic() + 2
            while not self.stopped.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(self.stopped.exists(), 'Scanner process group was not terminated')
            for marker in (self.opened, self.unquarantined, self.cached):
                self.assertFalse(marker.exists(), 'Abandoned scan changed file safety state')
            if self.cache_db.exists():
                with sqlite3.connect(self.cache_db) as connection:
                    self.assertEqual(connection.execute(
                        'SELECT COUNT(*) FROM clean_scans').fetchone()[0], 0)
            self.assertEqual(self.document.read_bytes(), b'%PDF-1.4\ntest document')
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stderr.close()

    def test_scanner_failures_while_parent_is_shutting_down_fail_closed(self):
        # The owner's lifetime pipe can close while ClamAV is still running.
        # Even a scanner that prints a clean-looking result and exits zero in
        # its SIGTERM handler must not approve a document after cancellation.
        shutdown_cases = (
            ('nonzero_shutdown_error',
             'print("scanner failed during shutdown", file=sys.stderr, flush=True); sys.exit(2)'),
            ('misleading_clean_shutdown',
             'print("document.pdf: OK", flush=True); sys.exit(0)'),
        )
        for case, shutdown_action in shutdown_cases:
            with self.subTest(case=case):
                for marker in (self.started, self.stopped, self.opened,
                               self.unquarantined, self.cached):
                    marker.unlink(missing_ok=True)
                self.scanner.write_text(
                    '#!' + sys.executable + '\n'
                    'import signal, sys, time\n'
                    'from pathlib import Path\n'
                    'def on_shutdown(signum, frame):\n'
                    '    Path(' + repr(str(self.stopped)) + ').write_text("shutdown observed")\n'
                    '    ' + shutdown_action + '\n'
                    'signal.signal(signal.SIGTERM, on_shutdown)\n'
                    'Path(' + repr(str(self.started)) + ').write_text("started")\n'
                    'while True: time.sleep(0.05)\n'
                )
                child = self.launch()
                try:
                    self.wait_for_start(child)
                    child.stdin.close()  # Simulate the owning native app closing.
                    status = child.wait(timeout=8)
                    self.assertNotEqual(status, 0, 'Shutdown scanner outcome was approved')
                    self.assertTrue(self.stopped.exists(),
                                    'Scanner shutdown failure was not exercised')
                    for marker in (self.opened, self.unquarantined, self.cached):
                        self.assertFalse(marker.exists(),
                                         'Shutdown failure changed file safety state')
                    if self.cache_db.exists():
                        with sqlite3.connect(self.cache_db) as connection:
                            self.assertEqual(connection.execute(
                                'SELECT COUNT(*) FROM clean_scans').fetchone()[0], 0)
                    self.assertEqual(self.document.read_bytes(), b'%PDF-1.4\ntest document')
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=5)
                    if not child.stdin.closed:
                        child.stdin.close()
                    child.stderr.close()

    def test_live_parent_allows_original_clean_scan_flow(self):
        child = self.launch(sleep='0.1')
        try:
            self.wait_for_start(child)
            code = child.wait(timeout=8)
            self.assertEqual(code, 0, child.stderr.read().decode())
            self.assertTrue(self.opened.exists())
            self.assertTrue(self.unquarantined.exists())
            self.assertTrue(self.cached.exists())
            self.assertFalse(self.stopped.exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=5)
            child.stdin.close()
            child.stderr.close()


if __name__ == '__main__':
    unittest.main()
