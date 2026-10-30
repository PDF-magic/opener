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
      for term in forbidden + ("Button {",):
        # Protection's buttons select in-memory comparison previews only.
        if filename == "ProtectionSettingsView.swift" and term.startswith("Button"):
          continue
        # Advanced Scanning's single confirmed metadata reset is not a
        # scanner-parameter editor or bypass. Forbid every other button.
        if filename == "AdvancedScanningSettingsView.swift" and term == "Button(":
          continue
        # The Browsers page has exactly one new optional download-scope
        # toggle. It saves consent metadata only and cannot approve a scan.
        if filename == "BrowsersSettingsView.swift" and term == "Toggle(":
          continue
        # Updates now has two explicit, user-initiated actions; keep all
        # scanner bypass and settings mutation prohibitions intact.
        if filename == "UpdatesSettingsView.swift" and term in ("Button(", "Process(", "URLSession"):
          continue
        with self.subTest(page=filename, forbidden=term):
          self.assertNotIn(term, source)
      if filename == "BrowsersSettingsView.swift":
        self.assertEqual(source.count("Toggle("), 1)
        self.assertEqual(source.count('Toggle("Scan Other Supported Files"'), 1)
        self.assertIn('ScanOtherSupportedFilesPreference.save(enabled)', source)
      if filename == "AdvancedScanningSettingsView.swift":
        self.assertEqual(source.count('Button("Restore Recommended Limits"'), 2)
        self.assertIn('Button("Cancel", role: .cancel)', source)
        self.assertIn("RecommendedScannerLimitsReset.restore()", source)
      if filename == "UpdatesSettingsView.swift":
        self.assertIn('Button("Check for Updates Now")', source)
        self.assertIn('Button("Update Signatures Now")', source)
        self.assertIn("lstat(script.path, &metadata)", source)
      if filename == "ProtectionSettingsView.swift":
        self.assertIn("selectedPreview = tier", source)
        self.assertNotIn("SelectedProtectionProfilePreference.save", source)


if __name__ == "__main__":
  unittest.main()
