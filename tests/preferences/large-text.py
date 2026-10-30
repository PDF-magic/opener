#!/usr/bin/env python3
"""Audit wrapping and scalable text in the native preferences pages."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp"
MAIN = APP / "MainPreferencesView.swift"
UPDATES = APP / "UpdatesSettingsView.swift"
CI = ROOT / ".github" / "workflows" / "ci.yml"

PAGES = (
    "GeneralSettingsView.swift",
    "BrowsersSettingsView.swift",
    "ProtectionSettingsView.swift",
    "AdvancedScanningSettingsView.swift",
    "UpdatesSettingsView.swift",
    "AboutAndDiagnosticsSettingsView.swift",
    "ExtensionsAndIntegrationsSettingsView.swift",
)


class LargeTextPreferencesTests(unittest.TestCase):
  def test_sidebar_width_scales_and_long_labels_can_wrap(self):
    source = MAIN.read_text(encoding="utf-8")
    self.assertIn("@ScaledMetric(relativeTo: .body)", source)
    self.assertIn(".frame(minWidth: sidebarMinimumWidth)", source)
    self.assertIn("Label(section.title, systemImage: section.symbolName)", source)
    self.assertIn(".lineLimit(nil)", source)
    self.assertIn(".fixedSize(horizontal: false, vertical: true)", source)
    self.assertNotIn(".frame(minWidth: 170)", source)
    self.assertIn("NavigationSplitView", source)
    self.assertIn("List(MainPreferenceSection.allCases", source)

  def test_each_existing_settings_page_can_scroll_text(self):
    for filename in PAGES:
      with self.subTest(page=filename):
        content = (APP / filename).read_text(encoding="utf-8")
        self.assertIn("ScrollView {", content)
        self.assertIn(".font(.largeTitle", content)
        self.assertNotIn(".lineLimit(1)", content)
        self.assertNotIn(".truncationMode(", content)
        self.assertNotIn(".minimumScaleFactor(", content)
        self.assertNotIn(".frame(width:", content)
        self.assertNotIn(".frame(height:", content)

  def test_version_row_stacks_instead_of_truncating(self):
    source = UPDATES.read_text(encoding="utf-8")
    self.assertIn("ViewThatFits(in: .horizontal)", source)
    self.assertIn('LabeledContent("Installed version", value: applicationVersion)', source)
    self.assertIn("VStack(alignment: .leading, spacing: 4)", source)
    self.assertIn('Text("Installed version")', source)
    self.assertIn("Text(applicationVersion)", source)
    self.assertIn(".fixedSize(horizontal: false, vertical: true)", source)

  def test_macos_build_exercises_dynamic_type_layouts(self):
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("test-preferences-large-text.swift", ci)
    self.assertIn("test-preferences-large-text.py -v", ci)
    self.assertIn("PDFMagicOpenerApp/*SettingsView.swift", ci)


if __name__ == "__main__":
  unittest.main()
