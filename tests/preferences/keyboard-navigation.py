#!/usr/bin/env python3
"""Verify native, bounded keyboard navigation of the preferences sidebar."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
NAV = ROOT / "PDFMagicOpenerApp" / "MainPreferencesView.swift"
APP = ROOT / "PDFMagicOpenerApp" / "PDFMagicOpenerApp.swift"
README = ROOT / "README.md"


class PreferencesKeyboardNavigationTests(unittest.TestCase):
  def test_sidebar_is_focusable_and_focused_on_window_open(self):
    source = NAV.read_text(encoding="utf-8")
    for text in (
      "NavigationSplitView",
      "List(MainPreferenceSection.allCases, selection: $selection)",
      ".listStyle(.sidebar)",
      "@FocusState private var sidebarFocused: Bool",
      ".focused($sidebarFocused)",
      ".onAppear { sidebarFocused = true }",
      'accessibilityIdentifier("mainPreferencesSidebar")',
      "@State private var selection: MainPreferenceSection? = .general",
    ):
      with self.subTest(text=text):
        self.assertIn(text, source)

  def test_previous_and_next_shortcuts_change_section_without_wrapping(self):
    source = NAV.read_text(encoding="utf-8")
    for text in (
      'Label("Previous Section", systemImage: "chevron.up")',
      'Label("Next Section", systemImage: "chevron.down")',
      '.keyboardShortcut("[", modifiers: .command)',
      '.keyboardShortcut("]", modifiers: .command)',
      "moveSelection(by: -1)",
      "moveSelection(by: 1)",
      "sections.indices.contains(nextIndex)",
      "selection = sections[nextIndex]",
      "sidebarFocused = true",
      ".disabled(selectedIndex == 0)",
      ".disabled(selectedIndex == visibleSections.count - 1)",
      "visibleSections.firstIndex(of: selection ?? .general)",
      "let sections = visibleSections",
      "MainPreferenceSection.allCases.filter { $0 != .scanHistory || scanHistoryEnabled }",
      "ToolbarItemGroup",
    ):
      with self.subTest(text=text):
        self.assertIn(text, source)
    self.assertNotIn("sections.count - 1) %", source)

  def test_navigation_reuses_existing_pages_without_side_effects(self):
    source = NAV.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    for route in (
      "GeneralSettingsView()",
      "BrowsersSettingsView()",
      "ProtectionSettingsView()",
      "AdvancedScanningSettingsView()",
      "UpdatesSettingsView()",
      "AboutAndDiagnosticsSettingsView()",
    ):
      with self.subTest(route=route):
        self.assertIn(route, source)
    self.assertIn('Settings {\n      MainPreferencesView()', app)
    for forbidden in (
      "Process(", "NSWorkspace", "FileHandle(", "UserDefaults",
      "write(to:", "removeItem(", "LSSetDefault", "clamscan",
      "target-app.txt", "onOpenURL", "NSEvent.addGlobalMonitor",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)

  def test_keyboard_usage_is_documented(self):
    readme = README.read_text(encoding="utf-8")
    for term in ("Keyboard navigation (opener-0189)", "Tab/Shift-Tab",
                 "**⌘[**", "**⌘]**", "scanning policy"):
      with self.subTest(term=term):
        self.assertIn(term, readme)


if __name__ == "__main__":
  unittest.main()
