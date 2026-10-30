#!/usr/bin/env python3
"""Exercise immutable per-request security policy under concurrent scan changes."""
import importlib.util
import subprocess
import sys
import tempfile
import threading
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "scan_and_open", (Path(__file__).resolve().parents[2]s[2] / "scan-and-open.py"))
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class ActivePolicySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="opener-policy-snapshot-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.first = root / "first.pdf"
        self.second = root / "second.pdf"
        self.first.write_bytes(b"%PDF-1.4\npolicy test document")
        self.second.write_bytes(self.first.read_bytes())
        self.original = opener.ACTIVE_SCAN_POLICY.snapshot()
        self.addCleanup(opener.ACTIVE_SCAN_POLICY.activate, self.original)
        for name, value in (
            ("CACHE_DB", root / "clean-cache.sqlite3"),
            ("SCAN_REQUEST_DB", root / "requests.sqlite3"),
            ("intended_destination", "com.example.viewer"),
            ("pdf_fallback_application", None),
            ("read_signature_database_version", "known"),
            ("scan_engine_version", "1.0"),
        ):
            p = patch.object(opener, name, return_value=value) if callable(
                getattr(opener, name)) else patch.object(opener, name, value)
            p.start()
            self.addCleanup(p.stop)
        for name in ("verify_local_file_available", "verify_launch_target",
                     "remove_quarantine", "launch_clean_file"):
            p = patch.object(opener, name)
            p.start()
            self.addCleanup(p.stop)

    def test_hardening_never_disables_the_mandatory_security_floor(self):
        policy = opener.ScanSecurityPolicySnapshot()
        self.assertEqual(policy.pdf_timeout_seconds, opener.PDF_SCAN_TIMEOUT)
        self.assertEqual(policy.other_timeout_seconds, 180)
        with self.assertRaises(FrozenInstanceError):
            policy.pdf_timeout_seconds = 10
        for bad in (0, -1, True, 1.5, "10", None, 1801):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                opener.ScanSecurityPolicySnapshot(pdf_timeout_seconds=bad)
        for bad in (0, False, 1.5, "2", 181):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                opener.ScanSecurityPolicySnapshot(other_timeout_seconds=bad)
        for bad in ("built-in", {"pdf_timeout_seconds": 1}, None):
            with self.subTest(bad=bad), self.assertRaises(TypeError):
                opener.ACTIVE_SCAN_POLICY.activate(bad)
        self.assertIs(opener.ACTIVE_SCAN_POLICY.snapshot(), self.original)

    def test_policy_change_during_scan_affects_only_later_requests_and_cache(self):
        started, release = threading.Event(), threading.Event()
        recorded = []
        guard = threading.Lock()
        failures = []

        def run(command, timeout):
            with guard:
                recorded.append((Path(command[-1]).name, timeout, tuple(command)))
            if Path(command[-1]) == self.first:
                started.set()
                if not release.wait(10):
                    raise AssertionError("First scan never released")
            return subprocess.CompletedProcess(command, 0, "file: OK", "")

        def worker(document):
            try:
                opener.scan_and_open(str(document), "/scanner")
            except Exception as error:
                failures.append(error)

        with patch.object(opener, "run_scan_command", side_effect=run):
            thread = threading.Thread(target=worker, args=(self.first,))
            thread.start()
            try:
                self.assertTrue(started.wait(10), "First scan never entered ClamAV")
                tightened = opener.ScanSecurityPolicySnapshot(
                    pdf_timeout_seconds=35, other_timeout_seconds=25)
                opener.ACTIVE_SCAN_POLICY.activate(tightened)
                self.assertIs(opener.ACTIVE_SCAN_POLICY.snapshot(), tightened)
                # Same PDF bytes, but a changed effective security policy must
                # neither reuse the old cache nor inherit its timeout.
                worker(self.second)
            finally:
                release.set()
                thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), "Active request failed to finish")
        self.assertFalse(failures, failures)
        self.assertEqual(len(recorded), 2, recorded)
        self.assertEqual({name: timeout for name, timeout, _ in recorded},
                         {"first.pdf": opener.PDF_SCAN_TIMEOUT, "second.pdf": 35})
        for _, _, command in recorded:
            self.assertIn("--alert-encrypted=yes", command)
            self.assertIn("--alert-exceeds-max=yes", command)
            self.assertIn("--max-scantime=0", command)
            self.assertIn("--database=" + str(opener.DATABASE), command)
        old_key = opener.policy_cache_key(opener.fingerprint(self.first), True, self.original)
        new_key = opener.policy_cache_key(opener.fingerprint(self.first), True, tightened)
        self.assertNotEqual(old_key, new_key)
        self.assertEqual(old_key, opener.cache_key(opener.fingerprint(self.first), True))

    def test_queued_request_captures_policy_before_waiting_for_scan_slot(self):
        entered, release = threading.Event(), threading.Event()
        from contextlib import contextmanager

        @contextmanager
        def delayed_slot():
            entered.set()
            if not release.wait(10):
                raise AssertionError("Queue slot timed out in test")
            yield

        captured = []
        def run(command, timeout):
            captured.append(timeout)
            return subprocess.CompletedProcess(command, 0, "file: OK", "")

        with patch.object(opener, "scan_slot", delayed_slot), patch.object(
            opener, "run_scan_command", side_effect=run):
            thread = threading.Thread(
                target=lambda: opener.scan_and_open(str(self.first), "/scanner"))
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                opener.ACTIVE_SCAN_POLICY.activate(
                    opener.ScanSecurityPolicySnapshot(pdf_timeout_seconds=20))
            finally:
                release.set()
                thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(captured, [opener.PDF_SCAN_TIMEOUT],
                         "A queued request must retain its admission-time policy")

    def test_malware_detection_remains_blocked_after_policy_update(self):
        entered, release = threading.Event(), threading.Event()
        result = []
        def infected(command, timeout):
            entered.set()
            release.wait(10)
            return subprocess.CompletedProcess(command, 1, "file: Malware FOUND", "")

        def worker():
            try:
                opener.scan_and_open(str(self.first), "/scanner")
            except RuntimeError as error:
                result.append(str(error))

        with patch.object(opener, "run_scan_command", side_effect=infected), patch.object(
            opener, "remove_quarantine") as quarantine, patch.object(
            opener, "launch_clean_file") as launch:
            thread = threading.Thread(target=worker)
            thread.start()
            try:
                self.assertTrue(entered.wait(10))
                opener.ACTIVE_SCAN_POLICY.activate(
                    opener.ScanSecurityPolicySnapshot(pdf_timeout_seconds=10))
            finally:
                release.set()
                thread.join(timeout=10)
            quarantine.assert_not_called()
            launch.assert_not_called()
        self.assertEqual(result, ["Malware was detected; opening was stopped."])


if __name__ == "__main__":
    unittest.main()
