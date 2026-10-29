#!/usr/bin/env python3
"""Validate future optional scan concurrency without relaxing the installed two-slot gate."""
from pathlib import Path
import unittest

from configuration_validation import (
  MAX_PERMITTED_CONCURRENT_SCANS,
  SCANNER_CONCURRENCY_KEY,
  UnsupportedSettingValue,
  validate_configuration,
  validate_scanner_concurrency_limit,
)

ROOT = Path(__file__).resolve().parent


class ScannerConcurrencyLimitTests(unittest.TestCase):
  def test_permitted_limits_are_exact_integers(self):
    self.assertEqual(MAX_PERMITTED_CONCURRENT_SCANS, 2)
    for count in (1, 2):
      with self.subTest(count=count):
        self.assertEqual(validate_scanner_concurrency_limit(count), count)

  def test_rejects_out_of_range_noninteger_and_boolean_values(self):
    invalid = (0, -1, -100, 3, 4, 1000000, True, False, 1.0, 2.0,
               1.5, float("nan"), float("inf"), None, "1", "2", " 2",
               "", [], {}, (2,), b"2")
    for value in invalid:
      with self.subTest(value=repr(value)):
        with self.assertRaises(UnsupportedSettingValue):
          validate_scanner_concurrency_limit(value)

  def test_explicit_optional_setting_is_checked_before_preservation(self):
    defaults = {"version": 1, "showScanProgress": True}
    for count in (1, 2):
      saved = {SCANNER_CONCURRENCY_KEY: count, "future": {"custom": True}}
      with self.subTest(count=count):
        result = validate_configuration(saved, defaults=defaults)
        self.assertEqual(result[SCANNER_CONCURRENCY_KEY], count)
        self.assertEqual(result["future"], {"custom": True})
        self.assertEqual(saved[SCANNER_CONCURRENCY_KEY], count)
    for value in (0, 3, True, 2.0, "2", None):
      with self.subTest(value=repr(value)):
        with self.assertRaises(UnsupportedSettingValue):
          validate_configuration({SCANNER_CONCURRENCY_KEY: value}, defaults=defaults)

  def test_invalid_declared_defaults_and_saved_overrides_fail_closed(self):
    for bad_default in (0, 3, False, "2", 2.0):
      with self.subTest(default=repr(bad_default)):
        with self.assertRaises(UnsupportedSettingValue):
          validate_configuration({}, defaults={SCANNER_CONCURRENCY_KEY: bad_default})
    defaults = {"version": 1, SCANNER_CONCURRENCY_KEY: 2}
    self.assertEqual(validate_configuration({}, defaults=defaults), defaults)
    self.assertEqual(
      validate_configuration({SCANNER_CONCURRENCY_KEY: 1}, defaults=defaults)
      [SCANNER_CONCURRENCY_KEY], 1)
    for invalid in (0, 3, True, 1.5, "1"):
      with self.subTest(override=repr(invalid)):
        with self.assertRaises(UnsupportedSettingValue):
          validate_configuration({SCANNER_CONCURRENCY_KEY: invalid}, defaults=defaults)

  def test_does_not_modify_other_settings_or_live_scan_enforcement(self):
    defaults = {"version": 1, "showScanProgress": True}
    saved = {"showScanProgress": False, "future": {"custom": [1, 2]}}
    result = validate_configuration(saved, defaults=defaults)
    self.assertFalse(result["showScanProgress"])
    self.assertEqual(result["future"], {"custom": [1, 2]})
    result["future"]["custom"].append(3)
    self.assertEqual(saved["future"], {"custom": [1, 2]})
    self.assertEqual(defaults, {"version": 1, "showScanProgress": True})
    scan = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
    native = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
    self.assertIn("MAX_CONCURRENT_SCANS = 2", scan)
    self.assertIn("for index in range(MAX_CONCURRENT_SCANS):", scan)
    self.assertIn("private let maxConcurrentScans = 2", native)
    self.assertNotIn("configuration_validation", scan)
    self.assertNotIn("SCANNER_CONCURRENCY_KEY", native)

  def test_ci_runs_the_validator_regression(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    self.assertIn("python3 test-scanner-concurrency-limits.py -v", ci)


if __name__ == "__main__":
  unittest.main()
