#!/usr/bin/env python3
"""Verify the General PDF handler indicator is a read-only live status."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
GENERAL = (ROOT / "PDFMagicOpenerApp" / "GeneralSettingsView.swift").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
APP = (ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift").read_text(encoding="utf-8")


class GeneralPDFHandlerIndicatorTests(unittest.TestCase):
  def test_indicator_queries_pdf_association_not_browser_or_settings_app(self):
    for text in (
      "import CoreServices",
      "import UniformTypeIdentifiers",
      "LSCopyDefaultRoleHandlerForContentType(contentType as CFString, .all)",
      "UTType.pdf.identifier",
      'expectedPDFScanHandlerBundleID = "local.studio.brave-pdf-opener"',
      "enum GeneralPDFHandlerStatus: Equatable",
      "case isDefault", "case other(String)", "case unknown",
      "identifier == expectedPDFScanHandlerBundleID",
    ):
      with self.subTest(text=text):
        self.assertIn(text, GENERAL)
    self.assertNotIn("UTType.html", GENERAL)
    self.assertNotIn("local.studio.pdfmagicopener.swiftui", GENERAL)

  def test_indicator_is_in_general_and_refreshes_safely(self):
    for text in (
      'Label("Default PDF handler", systemImage: "doc.badge.gearshape")',
      'accessibilityIdentifier("defaultPDFHandlerSection")',
      'accessibilityIdentifier("defaultPDFHandlerStatus")',
      "@State private var pdfHandlerStatus: GeneralPDFHandlerStatus = .unknown",
      "NSApplication.didBecomeActiveNotification",
      "NotificationCenter.default.publisher(",
      ".onAppear(perform: refreshPDFHandlerStatus)",
      ".onReceive(",
      "pdfHandlerStatus = readGeneralPDFHandlerStatus()",
      "Read-only macOS PDF association status",
      "case .unknown:",
    ):
      with self.subTest(text=text):
        self.assertIn(text, GENERAL)
    self.assertIn('Picker("Browser for scanned PDFs", selection: Binding(', GENERAL)
    self.assertIn(".onAppear { loadBrowserSelection() }", GENERAL)
    self.assertIn("Settings {", APP)

  def test_lookup_never_changes_associations_or_user_settings(self):
    for forbidden in (
      "NSWorkspace", "Process(", "FileManager", "UserDefaults",
      "@AppStorage", "LSSetDefault", "setDefault", "clamscan(",
      "target-app.txt", "Button(", "write(to:",
      "URLSession", "onOpenURL", "DocumentGroup",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, GENERAL)

    self.assertEqual(GENERAL.count('Toggle("Show Scan Progress"'), 1)
    status = GENERAL.split('Label("Default PDF handler", systemImage:', 1)[1].split(
      '.accessibilityIdentifier("defaultPDFHandlerSection")', 1)[0]
    self.assertNotIn("Toggle(", status)

  def test_macos_ci_runs_real_swift_status_unit_tests(self):
    self.assertIn("test-general-pdf-handler-indicator.py -v", CI)
    self.assertIn("test-general-pdf-handler-indicator.swift", CI)
    self.assertIn("PDFMagicOpenerApp/GeneralSettingsView.swift", CI)


if __name__ == "__main__":
  unittest.main()
