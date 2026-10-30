#!/usr/bin/env python3
"""Validate internal scan concurrency without introducing user-editable parameters."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from scanner_concurrency_validation import (
    MAX_PERMITTED_CONCURRENT_SCANS,
    validate_scanner_concurrency_limit,
)

ROOT = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("scan_and_open", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class ScannerConcurrencyLimitTests(unittest.TestCase):
    def test_permitted_internal_limits_are_exact_integers(self):
        self.assertEqual(MAX_PERMITTED_CONCURRENT_SCANS, 2)
        for count in (1, 2):
            with self.subTest(count=count):
                self.assertEqual(validate_scanner_concurrency_limit(count), count)

    def test_invalid_limits_fail_closed_without_coercion(self):
        invalid = (0, -1, -100, 3, 4, 1000000, True, False, 1.0, 2.0,
                   1.5, float("nan"), float("inf"), None, "1", "2", " 2",
                   "", [], {}, (2,), b"2")
        for value in invalid:
            with self.subTest(value=repr(value)):
                with self.assertRaisesRegex(ValueError, "Unsupported scanner concurrency limit"):
                    validate_scanner_concurrency_limit(value)

    def test_unsafe_gate_values_are_rejected_before_any_slot_files_are_created(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.sqlite3"
            with patch.object(opener, "CACHE_DB", cache):
                for invalid in (0, -1, 3, True, False, 2.0, "2", None):
                    with self.subTest(value=repr(invalid)):
                        with patch.object(opener, "MAX_CONCURRENT_SCANS", invalid):
                            with self.assertRaisesRegex(ValueError, "Unsupported scanner concurrency limit"):
                                with opener.scan_slot():
                                    self.fail("Invalid concurrency reached the scanner queue")
                            self.assertFalse((Path(directory) / "scan-slots").exists())

    def test_lower_internal_limit_honors_one_slot_without_changing_default(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.sqlite3"
            started = threading.Event()
            acquired = threading.Event()

            def waiter():
                started.set()
                with opener.scan_slot():
                    acquired.set()

            with patch.object(opener, "CACHE_DB", cache):
                with patch.object(opener, "MAX_CONCURRENT_SCANS", 1):
                    with opener.scan_slot():
                        thread = threading.Thread(target=waiter, daemon=True)
                        thread.start()
                        self.assertTrue(started.wait(2))
                        self.assertFalse(acquired.wait(0.15), "One-slot limit was bypassed")
                    self.assertTrue(acquired.wait(2), "Waiting scan did not resume")
                    thread.join(timeout=2)
                    self.assertFalse(thread.is_alive())
            self.assertEqual(opener.MAX_CONCURRENT_SCANS, 2)

    def test_no_user_editable_setting_or_existing_two_slot_policy_change(self):
        gate = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        native = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
        prefs = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text(encoding="utf-8")
        validator = (ROOT / "configuration_validation.py").read_text(encoding="utf-8")
        self.assertIn("MAX_CONCURRENT_SCANS = 2", gate)
        self.assertIn("validate_scanner_concurrency_limit(MAX_CONCURRENT_SCANS)", gate)
        self.assertIn("for index in range(MAX_CONCURRENT_SCANS):", gate)
        self.assertIn("private let maxConcurrentScans = 2", native)
        # The opt-in reset can remove an inactive override; only the
        # installed scanner owns its enforced two-slot policy.
        self.assertIn('static let concurrencyOverrideKey = "maxConcurrentScans"', prefs)
        self.assertIn("defaults.removeObject(forKey: concurrencyOverrideKey)", prefs)
        self.assertNotIn(
            "maxConcurrentScans", prefs.split("enum RecommendedScannerLimitsReset", 1)[0]
        )
        self.assertNotIn("maxConcurrentScans", validator)
        self.assertNotIn("scanner_concurrency_validation", validator)
        self.assertNotIn("scanner_concurrency_validation", native)

    def test_ci_runs_the_regression(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/run-test.py tests/scanner/concurrency-limits.py -v", ci)


if __name__ == "__main__":
    unittest.main()
