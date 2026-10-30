#!/usr/bin/env python3
"""Hermetic tests for strict supported values and missing-key defaults."""
import unittest
from configuration_validation import UnsupportedSettingValue, validate_configuration

DEFAULTS = {
  "version": 1,
  "showScanProgress": True,
  "showSuccessfulScanNotifications": False,
  "showBlockedFileNotifications": False,
  "browser": "com.brave.Browser",
}


class ConfigurationValueTests(unittest.TestCase):
  def test_missing_keys_use_safe_defaults(self):
    actual = validate_configuration({"version": 1}, defaults=DEFAULTS)
    self.assertEqual(actual, DEFAULTS)
    self.assertIsNot(actual, DEFAULTS)

  def test_explicit_preferences_are_preserved(self):
    saved = {"version": 1, "showScanProgress": False,
             "showBlockedFileNotifications": True, "future": {"flag": False}}
    actual = validate_configuration(saved, defaults=DEFAULTS)
    self.assertFalse(actual["showScanProgress"])
    self.assertTrue(actual["showBlockedFileNotifications"])
    self.assertEqual(actual["future"], {"flag": False})
    actual["future"]["flag"] = True
    self.assertEqual(saved["future"], {"flag": False})

  def test_rejects_unsupported_types_including_bool_integer_confusion(self):
    for key, value in (("version", True), ("version", "1"),
                       ("showScanProgress", 1), ("showScanProgress", "false"),
                       ("showSuccessfulScanNotifications", None),
                       ("showBlockedFileNotifications", []), ("browser", 99)):
      with self.subTest(key=key, value=value):
        with self.assertRaises(UnsupportedSettingValue):
          validate_configuration({key: value}, defaults=DEFAULTS)

  def test_enum_limits_supported_values_without_changing_custom_settings(self):
    choices = {"version": (1,), "browser": ("com.brave.Browser", "com.apple.Preview")}
    self.assertEqual(validate_configuration({"browser": "com.apple.Preview"},
                      defaults=DEFAULTS, allowed_values=choices)["browser"], "com.apple.Preview")
    for candidate in ("unsupported", "", "system-unverified"):
      with self.subTest(candidate=candidate), self.assertRaises(UnsupportedSettingValue):
        validate_configuration({"browser": candidate}, defaults=DEFAULTS, allowed_values=choices)
    with self.assertRaises(UnsupportedSettingValue):
      validate_configuration({"version": 2}, defaults=DEFAULTS, allowed_values=choices)

  def test_bad_contracts_are_rejected(self):
    with self.assertRaises(TypeError):
      validate_configuration([], defaults=DEFAULTS)
    with self.assertRaises(ValueError):
      validate_configuration({}, defaults=DEFAULTS, allowed_values={"unknown": [True]})


if __name__ == "__main__":
  unittest.main()
