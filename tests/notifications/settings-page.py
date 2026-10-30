#!/usr/bin/env python3
"""Verify the Notifications page exists, navigates correctly, and cannot change scan policy."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "PDFMagicOpenerApp"
MAIN = APP / "MainPreferencesView.swift"
PAGE = APP / "NotificationsSettingsView.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"


class NotificationsSettingsPageTests(unittest.TestCase):
  def test_sidebar_includes_notifications_and_routes_to_dedicated_view(self):
    src = MAIN.read_text(encoding="utf-8")
    for required in (
        "case notifications",
        'case .notifications: return "Notifications"',
        'case .notifications: return "bell.badge"',
        "List(MainPreferenceSection.allCases",
        'accessibilityIdentifier("mainPreferencesSidebar")',
    ):
      with self.subTest(required=required):
        self.assertIn(required, src)
    self.assertRegex(src, r"case \.notifications:\s+NotificationsSettingsView\(\)")
    for previous in ("case general", "case browsers", "case security",
                     "GeneralSettingsView()", "ProtectionSettingsView()"):
      self.assertIn(previous, src)

  def test_page_is_meaningful_and_accessible(self):
    src = PAGE.read_text(encoding="utf-8")
    for required in (
        "import SwiftUI", "struct NotificationsSettingsView: View",
        'Text("Notifications")',
        'GroupBox("Scan progress")',
        'GroupBox("Scan results")',
        'GroupBox("System notifications")',
        'accessibilityIdentifier("notificationsSettingsPage")',
        'accessibilityIdentifier("scanProgressNotificationsSection")',
        'accessibilityIdentifier("scanResultNotificationsSection")',
        'accessibilityIdentifier("systemNotificationsSection")',
        "Not configured yet",
        "No notification permission is requested",
        "informational",
    ):
      with self.subTest(required=required):
        self.assertIn(required, src)

  def test_page_is_read_only_and_has_no_unimplemented_controls(self):
    src = PAGE.read_text(encoding="utf-8")
    for forbidden in (
        "Toggle(", "Button(", "Picker(", "UserDefaults", "@AppStorage",
        "UNUserNotificationCenter", "requestAuthorization", "NSWorkspace",
        "NSApplication.shared", "Process(", "FileHandle(", "write(to:",
        "createFile(", "removeItem(", "LSSetDefault", "clamscan",
        "target-app.txt", "DocumentGroup", "onOpenURL",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, src)

  def test_view_is_in_native_preferences_target_exactly_once(self):
    src = PROJECT.read_text(encoding="utf-8")
    self.assertEqual(src.count("path = NotificationsSettingsView.swift;"), 1)
    self.assertEqual(src.count("B18300000000000000000001 = {"), 1)
    self.assertEqual(src.count("B18300000000000000000002 = {"), 1)
    self.assertRegex(src, r"B18300000000000000000001\s*=\s*\{\s*isa = PBXBuildFile;\s*fileRef = B18300000000000000000002;")
    group = re.search(r"A10000000000000000000006\s*=\s*\{.*?children = \((.*?)\);", src, re.S)
    sources = re.search(r"A10000000000000000000009\s*=\s*\{.*?files = \((.*?)\);", src, re.S)
    self.assertIsNotNone(group)
    self.assertIsNotNone(sources)
    self.assertEqual(group.group(1).count("B18300000000000000000002"), 1)
    self.assertEqual(sources.group(1).count("B18300000000000000000001"), 1)
    self.assertNotIn("CFBundleDocumentTypes", src)


if __name__ == "__main__":
  unittest.main()
