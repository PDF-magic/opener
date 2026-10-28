#!/usr/bin/env python3
"""Verify the SwiftUI About window, app version, and bundled AGPL-3 license."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
ABOUT = ROOT / "PDFMagicOpenerApp" / "AboutView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
LICENSE = ROOT / "LICENSE"


class AboutWindowTests(unittest.TestCase):
  def test_about_is_accessible_from_the_application_menu(self):
    entry = APP.read_text(encoding="utf-8")
    self.assertIn('Window("About PDF Magic Opener", id: "about")', entry)
    self.assertIn("AboutView()", entry)
    self.assertIn("CommandGroup(replacing: .appInfo)", entry)
    self.assertIn('Button("About PDF Magic Opener")', entry)
    self.assertIn('openWindow(id: "about")', entry)

  def test_version_is_read_from_built_bundle_metadata(self):
    source = ABOUT.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn('object(forInfoDictionaryKey: "CFBundleShortVersionString")', source)
    self.assertIn('Text("Version \\(version)")', source)
    self.assertEqual(project.count("MARKETING_VERSION = 0.1.0;"), 2)
    self.assertEqual(project.count("CURRENT_PROJECT_VERSION = 1;"), 2)

  def test_full_license_is_available_offline(self):
    source = ABOUT.read_text(encoding="utf-8")
    project = PROJECT.read_text(encoding="utf-8")
    license_text = LICENSE.read_text(encoding="utf-8")
    self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", license_text)
    self.assertIn("Version 3, 19 November 2007", license_text)
    self.assertIn("GNU Affero General Public License, Version 3 (AGPL-3.0)", source)
    self.assertIn("ABSOLUTELY NO WARRANTY", source)
    self.assertIn('url(forResource: "LICENSE", withExtension: nil)', source)
    self.assertIn("View Full License", source)
    self.assertIn("lastKnownFileType = text;\n      path = LICENSE;", project)
    self.assertIn("files = (A10000000000000000000018,);", project)
    self.assertIn("path = AboutView.swift;", project)

  def test_about_does_not_mutate_pdf_scan_or_destination(self):
    source = ABOUT.read_text(encoding="utf-8")
    for forbidden in ("NSWorkspace.shared", "onOpenURL(", "Process()", "clamscan(", "FileManager.default.removeItem"):
      self.assertNotIn(forbidden, source)


if __name__ == "__main__":
  unittest.main()
