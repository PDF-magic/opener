#!/usr/bin/env python3
"""Regress the narrow native browser preferences deep-link contract."""
import plistlib
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
SCHEME = "pdfmagicopener"
URL = "pdfmagicopener://preferences"


class BrowserPreferencesDeepLinkTests(unittest.TestCase):
  def test_exact_scheme_and_not_a_pdf_handler(self):
    with (ROOT / "PDFMagicOpenerApp" / "Info.plist").open("rb") as f:
      info = plistlib.load(f)
    self.assertEqual(info["CFBundleURLTypes"], [{
      "CFBundleURLName": "local.studio.pdfmagicopener.preferences",
      "CFBundleURLSchemes": [SCHEME],
    }])
    self.assertNotIn("CFBundleDocumentTypes", info)

  def test_only_exact_preference_request_is_handled(self):
    app = (ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift").read_text()
    self.assertIn(f'url.absoluteString == "{URL}"', app)
    self.assertIn("NSApplication.shared.activate(ignoringOtherApps: true)", app)
    self.assertIn("MainPreferencesView()", app)
    self.assertNotIn("NSWorkspace.shared.open(url)", app)

  def test_safari_popup_resource_uses_shared_exact_file(self):
    xcode = (ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj").read_text()
    self.assertIn("path = extensions/webextension/preferences.html;", xcode)
    self.assertIn("files = (D56700000000000000000003, D57700000000000000000001,);", xcode)

  def test_popup_cannot_claim_a_scan_verdict(self):
    text = (ROOT / "extensions/webextension/preferences.html").read_text()
    self.assertIn('href="pdfmagicopener://preferences"', text)
    self.assertIn("Browser PDF scanning and opening are not active", text)
    self.assertNotIn("<script", text)
    self.assertNotIn("onclick=", text)


def verify_built_app(app):
  with (app / "Contents/Info.plist").open("rb") as f:
    info = plistlib.load(f)
  assert info["CFBundleURLTypes"] == [{
    "CFBundleURLName": "local.studio.pdfmagicopener.preferences",
    "CFBundleURLSchemes": [SCHEME],
  }]
  assert "CFBundleDocumentTypes" not in info
  popup = ROOT / "extensions/webextension/preferences.html"
  safari = app / "Contents/PlugIns/PDFMagicOpenerSafari.appex/Contents/Resources/preferences.html"
  assert safari.read_bytes() == popup.read_bytes(), "Safari popup resource diverges"


if __name__ == "__main__":
  if len(sys.argv) == 3 and sys.argv[1] == "--verify-built-app":
    verify_built_app(Path(sys.argv[2]))
  else:
    unittest.main()
