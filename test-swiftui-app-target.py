#!/usr/bin/env python3
"""Assert the new SwiftUI target stays separate from the current PDF scan gate."""

from pathlib import Path
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
SCHEME = ROOT / "PDFMagicOpener.xcodeproj" / "xcshareddata" / "xcschemes" / "PDFMagicOpener.xcscheme"
SOURCE = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"


class SwiftUIAppTargetTests(unittest.TestCase):
  def test_app_target_is_separate_from_existing_pdf_handler(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn('productType = "com.apple.product-type.application";', project)
    self.assertIn("PRODUCT_BUNDLE_IDENTIFIER = local.studio.pdfmagicopener.swiftui;", project)
    self.assertNotIn("PRODUCT_BUNDLE_IDENTIFIER = local.studio.brave-pdf-opener;", project)
    self.assertIn("GENERATE_INFOPLIST_FILE = YES;", project)
    self.assertIn("PDFMagicOpenerApp.swift", project)
    self.assertNotIn("CFBundleDocumentTypes", project)
    self.assertNotIn("UTImportedTypeDeclarations", project)

  def test_swiftui_entry_point_is_a_window_not_a_document_handler(self):
    source = SOURCE.read_text(encoding="utf-8")
    for required in ("import SwiftUI", "@main", "struct PDFMagicOpenerApp: App", "WindowGroup"):
      self.assertIn(required, source)
    for forbidden in ("NSWorkspace", "onOpenURL", "DocumentGroup", "clamscan", "target-app.txt"):
      self.assertNotIn(forbidden, source)

  def test_shared_xcode_scheme_builds_the_application(self):
    xml = ET.parse(SCHEME).getroot()
    self.assertEqual(xml.tag, "Scheme")
    refs = xml.findall(".//BuildableReference")
    self.assertTrue(refs)
    for ref in refs:
      self.assertEqual(ref.attrib["BuildableName"], "PDFMagicOpener.app")
      self.assertEqual(ref.attrib["BlueprintIdentifier"], "A10000000000000000000008")


if __name__ == "__main__":
  unittest.main()
