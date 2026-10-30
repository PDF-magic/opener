#!/usr/bin/env python3
"""Guard the intentional absence of a persistent menu-bar status item."""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
APP_DIR = ROOT / "PDFMagicOpenerApp"
APP = APP_DIR / "PDFMagicOpenerApp.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
POLICY = ROOT / "docs" / "menu-bar-decision.md"


class MenuBarDecisionTests(unittest.TestCase):
  def test_no_status_item_or_background_agent(self):
    for source_file in sorted(APP_DIR.glob("*.swift")):
      source = source_file.read_text(encoding="utf-8")
      for forbidden in ("MenuBarExtra", "NSStatusBar", "NSStatusItem"):
        with self.subTest(path=source_file.name, forbidden=forbidden):
          self.assertNotIn(forbidden, source)
    project = PROJECT.read_text(encoding="utf-8")
    # A visible Dock app may explicitly set LSUIElement = NO. Reject only
    # accessory/background policies; neither creates a menu-bar status item.
    self.assertNotIn("INFOPLIST_KEY_LSUIElement = YES;", project)
    self.assertNotIn("INFOPLIST_KEY_LSBackgroundOnly = YES;", project)
    self.assertEqual(project.count("INFOPLIST_KEY_LSUIElement = NO;"), 2)

  def test_normal_preferences_and_quit_remain_available(self):
    app = APP.read_text(encoding="utf-8")
    self.assertIn('WindowGroup("PDF Magic Opener")', app)
    self.assertIn("MainPreferencesView()", app)
    self.assertIn('Button("Quit PDF Magic Opener")', app)
    self.assertIn('NSApplication.shared.terminate(nil)', app)

  def test_decision_is_explicit_and_revisitable(self):
    app = APP.read_text(encoding="utf-8")
    policy = POLICY.read_text(encoding="utf-8")
    self.assertIn("Menu bar decision (opener-0176)", app)
    self.assertIn("Decision: not enabled", policy)
    self.assertIn("separate installed AppKit/ClamAV handler", policy)
    self.assertIn("When to reconsider", policy)


if __name__ == "__main__":
  unittest.main()
