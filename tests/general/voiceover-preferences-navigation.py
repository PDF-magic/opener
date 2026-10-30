#!/usr/bin/env python3
"""Verify VoiceOver labels on the preferences navigation (opener-0190)."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"


class VoiceOverPreferencesNavigationTests(unittest.TestCase):
  def test_sidebar_has_a_spoken_group_label(self):
    source = VIEW.read_text(encoding="utf-8")
    self.assertIn('accessibilityLabel("Preferences sections")', source)
    self.assertIn('accessibilityIdentifier("mainPreferencesSidebar")', source)

  def test_every_navigation_row_has_a_dynamic_spoken_label_and_hint(self):
    source = VIEW.read_text(encoding="utf-8")
    self.assertRegex(
      source,
      r"(?s)Label\(section\.title, systemImage: section\.symbolName\)"
      r".*?\.tag\(section\)"
      r'.*?\.accessibilityLabel\("\\\(section\.title\) settings"\)'
      r'.*?\.accessibilityHint\("Show the \\\(section\.title\) settings page"\)',
    )
    self.assertIn("List(MainPreferenceSection.allCases, selection: $selection)", source)
    self.assertIn("switch selection ?? .general", source)
    self.assertIn("@State private var selection: MainPreferenceSection? = .general", source)

  def test_labels_apply_to_every_current_and_future_sidebar_destination(self):
    source = VIEW.read_text(encoding="utf-8")
    for case in re.findall(r"^  case ([A-Za-z][A-Za-z0-9]*)$", source, re.MULTILINE):
      with self.subTest(section=case):
        self.assertIn(f"case .{case}: return", source)
        self.assertRegex(source, rf"case \.{case}:\s+\w+SettingsView\(\)")
    self.assertNotIn("onChange(of: selection)", source)

  def test_voiceover_labels_do_not_change_scanning_or_preferences(self):
    source = VIEW.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    self.assertIn("MainPreferencesView()", app)
    for prohibited in (
      "@AppStorage", "UserDefaults", "FileManager", "Process(",
      "NSWorkspace", "onOpenURL", "DocumentGroup", "clamscan",
      "LSSetDefault", "target-app.txt", "write(to:", "setDefault",
    ):
      with self.subTest(prohibited=prohibited):
        self.assertNotIn(prohibited, source)


if __name__ == "__main__":
  unittest.main()
