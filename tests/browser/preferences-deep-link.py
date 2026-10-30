#!/usr/bin/env python3
"""Verify the user-initiated browser-to-native preferences URL boundary."""
from pathlib import Path
import plistlib
import sys
import unittest

ROOT = Path(__file__).resolve().parent
PREFERENCES_URL = "pdfmagicopener://preferences"
EXPECTED_URL_TYPES = [{
  "CFBundleURLName": "local.studio.pdfmagicopener.preferences",
  "CFBundleURLSchemes": ["pdfmagicopener"],
}]
POPUP = ROOT / "extensions/webextension/src/popup.html"


def verify_built_app(app: Path) -> None:
  """Check real host URL registration and bundled Safari static popup."""
  assert app.is_dir(), f"Missing built app: {app}"
  with (app / "Contents/Info.plist").open("rb") as f:
    info = plistlib.load(f)
  assert info["CFBundleURLTypes"] == EXPECTED_URL_TYPES
  assert "CFBundleDocumentTypes" not in info
  assert info["CFBundleIdentifier"] == "local.studio.pdfmagicopener.swiftui"
  bundle_popup = (app / "Contents/PlugIns/PDFMagicOpenerSafari.appex/"
                  "Contents/Resources/popup.html")
  assert bundle_popup.read_bytes() == POPUP.read_bytes(), (
    "Safari popup differs from shared source"
  )


class NativePreferencesLinkTests(unittest.TestCase):
  def test_scheme_is_registered_without_pdf_document_associations(self):
    with (ROOT / "PDFMagicOpenerApp/Info.plist").open("rb") as f:
      info = plistlib.load(f)
    self.assertEqual(info["CFBundleURLTypes"], EXPECTED_URL_TYPES)
    self.assertNotIn("CFBundleDocumentTypes", info)

  def test_exact_url_only_raises_existing_preferences_app(self):
    app = (ROOT / "PDFMagicOpenerApp/PDFMagicOpenerApp.swift").read_text()
    self.assertIn(f'url.absoluteString == "{PREFERENCES_URL}"', app)
    self.assertIn("NSApplication.shared.activate(ignoringOtherApps: true)", app)
    self.assertIn("MainPreferencesView()", app)
    self.assertNotIn("NSWorkspace.shared.open(url)", app)
    self.assertNotIn("openPDF(", app)

  def test_static_popup_never_issues_a_scan_verdict(self):
    text = POPUP.read_text(encoding="utf-8")
    link = ('<a id="openPDFMagicPreferences" '
            'href="pdfmagicopener://preferences">Open PDF Magic Preferences</a>')
    self.assertEqual(text.count(link), 1)
    self.assertIn("Not active", text)
    self.assertIn("cannot scan, sanitize, or open PDF files yet", text)
    for forbidden in ("<script", "<form", "<iframe", "onclick=", "https://"):
      self.assertNotIn(forbidden, text)

  def test_existing_ci_inspects_compiled_app_and_native_url_types(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("python3 scripts/run-test.py tests/browser/preferences-deep-link.py -v", ci)
    self.assertIn("python3 scripts/run-test.py tests/browser/preferences-deep-link.py --verify-built-app", ci)


if __name__ == "__main__":
  if len(sys.argv) == 3 and sys.argv[1] == "--verify-built-app":
    verify_built_app(Path(sys.argv[2]))
  else:
    unittest.main()
