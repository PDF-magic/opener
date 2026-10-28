#!/usr/bin/env python3
"""Check the documented persistent storage locations without touching user files."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class ConfigurationLocationTests(unittest.TestCase):
  def test_shared_user_defaults_domain_is_stable(self):
    source = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    self.assertIn('suiteName = "local.studio.pdf-magic-opener"', source)
    self.assertIn("UserDefaults(suiteName: suiteName)", source)
    self.assertIn("SuccessfulScanNotificationPreference", source)
    self.assertIn("static let suiteName = ScanProgressPreference.suiteName", source)

  def test_scanner_location_and_verified_browser_selection_match(self):
    installer = (ROOT / "install-allow-and-open.sh").read_text()
    chooser = (ROOT / "PDFMagicOpenerApp/DefaultPDFBrowserPreferences.swift").read_text()
    self.assertIn('install_dir="$HOME/Library/Application Support/Studio/allow-and-open"', installer)
    self.assertIn('.appendingPathComponent("Library/Application Support/Studio/allow-and-open", isDirectory: true)', chooser)
    self.assertIn('"$install_dir/target-app.txt"', installer)
    self.assertIn('openat(parentFD, "target-app.txt", O_RDONLY | O_NOFOLLOW)', chooser)
    self.assertIn("saveVerified(_ option:", chooser)
    self.assertIn("select-custom-pdf-application.py", chooser)
    self.assertNotIn('write(to: preferenceDirectory', chooser)

  def test_existing_customization_survives_reinstallation(self):
    installer = (ROOT / "install-allow-and-open.sh").read_text()
    self.assertIn("os.O_WRONLY | os.O_CREAT | os.O_EXCL", installer)
    self.assertIn("except FileExistsError:", installer)
    self.assertIn("pass", installer)

  def test_documented_locations_and_no_migration(self):
    doc = (ROOT / "docs/persistent-configuration-location.md").read_text()
    self.assertIn('UserDefaults(suiteName: "local.studio.pdf-magic-opener")', doc)
    self.assertIn("~/Library/Preferences/local.studio.pdf-magic-opener.plist", doc)
    self.assertIn("~/Library/Application Support/Studio/allow-and-open/", doc)
    self.assertIn("no migration, initialization, reset, overwrite", doc)


if __name__ == "__main__":
  unittest.main()
