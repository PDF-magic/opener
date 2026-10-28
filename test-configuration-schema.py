#!/usr/bin/env python3
"""Protect the versioned configuration contract without touching live scanner settings."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()


class ConfigurationSchemaContractTests(unittest.TestCase):
  def test_version_and_compatibility(self):
    for token in ("struct PDFMagicConfigurationSchema: Codable, Equatable",
                  "static let currentVersion = 1", "case schemaVersion",
                  "case showScanProgress", "case showSuccessfulScanNotifications",
                  "guard version == Self.currentVersion",
                  "decodeIfPresent(Bool.self", "encoder.outputFormatting = [.sortedKeys]"):
      self.assertIn(token, SOURCE)
    self.assertIn("test-configuration-schema.swift", CI)

  def test_legacy_preference_keys_and_defaults_remain_untouched(self):
    self.assertIn('key = "showScanProgress"', SOURCE)
    self.assertIn('key = "showSuccessfulScanNotifications"', SOURCE)
    self.assertIn('suiteName = "local.studio.pdf-magic-opener"', SOURCE)
    self.assertIn("return true", SOURCE)
    self.assertIn("return false", SOURCE)
    schema = SOURCE.split("struct PDFMagicConfigurationSchema", 1)[1]
    for forbidden in ("defaults.set(", "synchronize()", "clamscan", "target-app.txt",
                      "FileManager", "Process(", "NSWorkspace"):
      self.assertNotIn(forbidden, schema)


if __name__ == "__main__":
  unittest.main()
