#!/usr/bin/env python3
"""Regression tests separating ClamAV detection evidence from opening policy."""
from dataclasses import FrozenInstanceError
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


def result(code, stdout, stderr=''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class DetectionDecisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / 'test.pdf'
        self.file.write_bytes(b'%PDF-1.4\nTest')
        cache = patch.object(opener, 'CACHE_DB',
                             Path(self.temp.name) / 'clean.sqlite3')
        cache.start()
        self.addCleanup(cache.stop)
        # The version command is metadata; scan-policy tests isolate it so
        # command ordering assertions cover only the malware gate and launcher.
        version = patch.object(opener, 'scan_engine_version', return_value=None)
        version.start()
        self.addCleanup(version.stop)

    def test_detection_contains_only_evidence_and_cannot_be_modified(self):
        raw = result(1, 'file: Malware FOUND')
        evidence = opener.capture_detection(raw)
        self.assertEqual((evidence.exit_code, evidence.stdout, evidence.stderr),
                         (1, raw.stdout, ''))
        self.assertFalse(hasattr(evidence, 'allowed'))
        self.assertFalse(hasattr(evidence, 'reason'))
        with self.assertRaises(FrozenInstanceError):
            evidence.exit_code = 0
        decision = opener.decide_opening(evidence)
        self.assertIsInstance(decision, opener.OpeningDecision)
        self.assertFalse(decision.allowed)
        self.assertEqual(evidence, opener.capture_detection(raw))
        self.assertNotIn('Malware FOUND', decision.reason)

    def test_policy_preserves_exact_previous_scanner_gate(self):
        cases = (
            (0, 'file: OK', '', True),
            (0, 'file: OK\nother: Empty file', '', True),
            (1, 'file: Malware FOUND', '', False),
            (1, 'file: Heuristics.Limits.Exceeded.MaxFileSize FOUND', '', False),
            (2, 'file: OK', 'error', False),
            (0, '', '', False),
            (0, 'file: Empty file', '', False),
            (0, 'file: OK', 'WARNING: skipped input', False),
            (0, 'file: OK\nunscanned: skipped', '', False),
            (0, 'file: OK\nfile: Malware FOUND', '', False),
        )
        for code, stdout, stderr, expected in cases:
            with self.subTest(exit_code=code, stdout=stdout, stderr=stderr):
                evidence = opener.capture_detection(result(code, stdout, stderr))
                decision = opener.decide_opening(evidence)
                self.assertIs(decision.allowed, expected)
                self.assertIsNot(decision, evidence)
                if not expected:
                    self.assertTrue(decision.reason)

    def test_rejected_scan_cannot_remove_quarantine_or_launch(self):
        cases = (
            result(1, 'file: Malware FOUND'),
            result(2, 'file: OK', 'scanner failed'),
            result(0, 'file: Empty file'),
            result(0, 'file: OK', 'WARNING: skipped'),
        )
        for completed in cases:
            with self.subTest(code=completed.returncode, stdout=completed.stdout):
                with patch.object(opener.subprocess, 'run', return_value=completed) as run, \
                        patch.object(opener, 'remove_quarantine') as remove:
                    with self.assertRaises(RuntimeError):
                        opener.scan_and_open(str(self.file), '/scanner')
                self.assertEqual(run.call_count, 1)
                remove.assert_not_called()

    def test_clean_detection_does_not_override_file_change_gate(self):
        def run(command, **kwargs):
            self.file.write_bytes(b'changed while scanning')
            return result(0, 'file: OK')
        with patch.object(opener.subprocess, 'run', side_effect=run) as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(run.call_count, 1)
        remove.assert_not_called()

    def test_clean_detection_only_launches_after_quarantine_gate(self):
        events = []
        def run(command, **kwargs):
            events.append(command[0])
            return result(0, 'file: OK')
        with patch.object(opener.subprocess, 'run', side_effect=run), \
                patch.object(opener, 'remove_quarantine',
                             side_effect=lambda path: events.append('quarantine')):
            opener.scan_and_open(str(self.file), '/scanner')
        self.assertEqual(events, ['/scanner', 'quarantine', '/usr/bin/open'])

    def test_cached_clean_result_does_not_bypass_changed_file(self):
        opener.remember_clean(opener.cache_key(opener.fingerprint(self.file), True))
        original = opener.fingerprint
        calls = [0]
        def fingerprint(path):
            calls[0] += 1
            if calls[0] == 2:
                self.file.write_bytes(b'changed after cache lookup')
            return original(path)
        with patch.object(opener, 'fingerprint', side_effect=fingerprint), \
                patch.object(opener.subprocess, 'run') as run, \
                patch.object(opener, 'remove_quarantine') as remove:
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                opener.scan_and_open(str(self.file), '/scanner')
        run.assert_not_called()
        remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()
