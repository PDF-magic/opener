#!/usr/bin/env python3
"""opener-0555: explicit Maximum conversion-details action is preview-only."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp" / "ProtectionSettingsView.swift"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class MaximumConversionDetailsActionTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.source = VIEW.read_text(encoding="utf-8")

  def test_real_button_only_in_selected_maximum_preview(self):
    self.assertIn("if let selectedPreview {", self.source)
    self.assertEqual(self.source.count("Button(\"View Conversion Details\")"), 1)
    preview = self.source.split(
        'Text("This comparison lists planned tier requirements;', 1)[1].split(
        '.accessibilityIdentifier("protectionCardPreviewDetail")', 1)[0]
    self.assertIn("if selectedPreview == .maximum {", preview)
    self.assertIn('Button("View Conversion Details") {', preview)
    self.assertIn("showConversionDetails = true", preview)
    self.assertIn('.accessibilityIdentifier("maximumViewConversionDetails")', preview)
    self.assertIn("no document is converted or scanned", preview)

  def test_button_opens_dismissible_accessible_sheet(self):
    self.assertIn("@State private var showConversionDetails = false", self.source)
    self.assertIn(".sheet(isPresented: $showConversionDetails) {", self.source)
    self.assertIn("conversionDetailsSheet", self.source)
    details = self.source.split(
        "private var conversionDetailsSheet: some View {", 1)[1].split(
        "\n  private func includedCheckDetail(", 1)[0]
    for text in (
        'Text("Maximum conversion details")',
        "Preview only", "Maximum protection is not available",
        "No PDF has been converted, saved, scanned or opened",
        'GroupBox("How the generated copy is made")',
        'GroupBox("What can change or be removed")',
        'GroupBox("Safety checks before opening")',
        "separate visual-only PDF",
        "untouched original remains unchanged",
        "Selectable and searchable text",
        "OCR is not restored",
        "invalidate digital signatures",
        "not a malware-clean verdict",
        "requires its own fresh scan",
        "must not be opened as a fallback",
        "not results for a selected PDF",
        'Button("Done")',
        "showConversionDetails = false",
        ".keyboardShortcut(.defaultAction)",
        '.accessibilityIdentifier("maximumConversionDetailsClose")',
        '.accessibilityIdentifier("maximumConversionDetailsSheet")',
        ".fixedSize(horizontal: false, vertical: true)",
    ):
      with self.subTest(text=text):
        self.assertIn(text, details)

  def test_presentation_has_no_file_or_scanner_side_effects(self):
    details = self.source.split(
        "private var conversionDetailsSheet: some View {", 1)[1].split(
        "\n  private func includedCheckDetail(", 1)[0]
    for forbidden in (
        "FileManager", "UserDefaults", "Process(", "NSWorkspace",
        "FileHandle(", "URLSession", "scan_and_open", "write(to:",
        "saveProtectionPreview", "resetProtectionPreview", "clamscan",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, details)
    self.assertIn("Active protection: Built-in ClamAV", self.source)
    self.assertIn("Preview only · Not available as an active policy", self.source)

  def test_ci_runs_action_regressions_and_native_app_build(self):
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("python3 tests/maximum/conversion-details-action.py -v", ci)
    self.assertIn("python3 tests/protection/settings-cards.py -v", ci)
    self.assertIn("macos-build:", ci)
    self.assertIn("xcodebuild", ci)


if __name__ == "__main__":
  unittest.main()
