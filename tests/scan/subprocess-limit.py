#!/usr/bin/env python3
"""opener-0853: bound scanner subprocess probes across requests and processes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
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
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scanner_process_limit", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ScannerSubprocessLimitTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="scanner-subprocess-limit-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        substitution = patch.object(gate, "CACHE_DB", self.root / "clean.sqlite3")
        substitution.start()
        self.addCleanup(substitution.stop)

    def test_unqueued_version_probes_obey_two_active_process_slots(self):
        counter = threading.Lock()
        active = 0
        peak = 0

        def version_process(*args, **kwargs):
            nonlocal active, peak
            with counter:
                active += 1
                peak = max(peak, active)
            time.sleep(0.09)
            with counter:
                active -= 1
            return "ClamAV 1.5.4/28765"

        with patch.object(gate.subprocess, "check_output", side_effect=version_process) as run:
            with ThreadPoolExecutor(max_workers=7) as pool:
                versions = list(pool.map(gate.scan_engine_version, ["/scanner"] * 7))
        self.assertEqual(versions, ["1.5.4"] * 7)
        self.assertEqual(peak, gate.MAX_CONCURRENT_SCANS)
        self.assertEqual(active, 0)
        self.assertEqual(run.call_count, 7)

    def test_busy_scan_slots_block_an_unqueued_child_process(self):
        started = threading.Event()
        launched = threading.Event()

        def probe():
            started.set()
            return gate.scan_engine_version("/scanner")

        def record_child(*args, **kwargs):
            launched.set()
            return "ClamAV 1.5.4/28765"

        with patch.object(gate.subprocess, "check_output", side_effect=record_child):
            with ThreadPoolExecutor(max_workers=1) as pool:
                with gate.scan_slot():
                    with gate.scan_slot():
                        future = pool.submit(probe)
                        self.assertTrue(started.wait(2))
                        self.assertFalse(launched.wait(0.15),
                                         "Version child bypassed the shared scan slots")
                    self.assertTrue(launched.wait(2))
                self.assertEqual(future.result(timeout=2), "1.5.4")

    def test_scan_owned_version_probe_does_not_acquire_another_slot(self):
        with gate.scan_slot():
            with gate.scan_slot():
                with patch.object(gate, "scan_slot",
                                  side_effect=AssertionError("nested scan slot")) as nested, \
                     patch.object(gate.subprocess, "check_output",
                                  return_value="ClamAV 1.5.4/28765") as run:
                    self.assertEqual(gate.scan_engine_version("/scanner"), "1.5.4")
                nested.assert_not_called()
                run.assert_called_once_with(["/scanner", "--version"], text=True,
                                            timeout=5, stderr=subprocess.DEVNULL)

    def test_failed_probe_releases_slot_and_remains_unknown(self):
        with patch.object(gate.subprocess, "check_output",
                          side_effect=subprocess.TimeoutExpired("/scanner", 5)):
            self.assertIsNone(gate.scan_engine_version("/scanner"))
        with patch.object(gate.subprocess, "check_output",
                          return_value="ClamAV 1.4.6/28765"):
            self.assertEqual(gate.scan_engine_version("/scanner"), "1.4.6")

    def test_concurrency_limit_is_not_user_editable_or_weakened(self):
        self.assertEqual(gate.MAX_CONCURRENT_SCANS, 2)
        self.assertIn("with scan_slot():", (ROOT / "scan-and-open.py").read_text())


if __name__ == "__main__":
    unittest.main()
