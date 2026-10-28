#!/usr/bin/env python3
"""Verify visible and accessible help for technical preferences topics."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP = ROOT / "PDFMagicOpenerApp"


class TechnicalPreferencesHelpTests(unittest.TestCase):
  def test_contextual_help_is_visible_in_scanner_browser_and_protection_sections(self):
    pages = {
        "ProtectionSettingsView.swift": (
            "ClamAV is a local malware scanner",
            "Fail-closed means an interrupted",
            "Handoff is the step that opens a verified file",
        ),
        "AdvancedScanningSettingsView.swift": (
            "Malware signatures are local definitions",
            "A cloud placeholder or unfinished download",
            "An inconclusive or interrupted scan is not a clean result",
        ),
        "BrowsersSettingsView.swift": (
            "Discovery lists installed apps",
            "Your preferred PDF destination is separate",
            "A custom application is a saved destination choice",
        ),
    }
    for filename, explanations in pages.items():
      with self.subTest(page=filename):
        source = (APP / filename).read_text(encoding="utf-8")
        for explanation in explanations:
          self.assertIn(explanation, source)
        self.assertEqual(source.count("helpText: \""), 3)
        self.assertIn('Label(helpText, systemImage: "info.circle")', source)
        self.assertIn(".font(.footnote)", source)
        self.assertIn(".fixedSize(horizontal: false, vertical: true)", source)
        self.assertIn(".help(helpText)", source)

  def test_updates_distinguishes_application_updates_from_signature_updates(self):
    source = (APP / "UpdatesSettingsView.swift").read_text(encoding="utf-8")
    self.assertIn("installed version comes from this app bundle", source)
    self.assertIn("Their update schedule is separate from app updates", source)
    self.assertIn('GroupBox("Application updates")', source)
    self.assertIn('GroupBox("Malware definition updates")', source)
    self.assertEqual(source.count('systemImage: "info.circle"'), 2)
    self.assertIn('LabeledContent("Installed version", value: applicationVersion)', source)

  def test_help_is_non_mutating_and_never_approves_scans(self):
    pages = (
        "ProtectionSettingsView.swift",
        "AdvancedScanningSettingsView.swift",
        "BrowsersSettingsView.swift",
        "UpdatesSettingsView.swift",
    )
    forbidden = (
        "Toggle(", "Button(", "Picker(", "Slider(", "@AppStorage",
        "UserDefaults", "FileHandle(", "Process(", "NSWorkspace",
        "write(to:", "LSSetDefault", "setDefault", "target-app.txt",
        "onOpenURL", "clamscan(", "URLSession",
    )
    for filename in pages:
      source = (APP / filename).read_text(encoding="utf-8")
      for term in forbidden:
        with self.subTest(page=filename, forbidden=term):
          self.assertNotIn(term, source)


if __name__ == "__main__":
  unittest.main()
