#!/usr/bin/env python3
"""Check private-only, explicitly confirmed Clear History wiring."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MAIN = (ROOT / "PDFMagicOpenerApp/MainPreferencesView.swift").read_text()
PAGE = (ROOT / "PDFMagicOpenerApp/ScanHistorySettingsView.swift").read_text()
DELETE = (ROOT / "PDFMagicOpenerApp/ClearScanHistory.swift").read_text()
READER = (ROOT / "PDFMagicOpenerApp/RecentScanHistory.swift").read_text()
PROJECT = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()

class ClearHistoryActionTests(unittest.TestCase):
  def test_ui_requires_destructive_confirmation_and_preserves_opt_in(self):
    self.assertIn("init(scanHistoryEnabled: Bool = false)", MAIN)
    self.assertIn("if section != .scanHistory || scanHistoryEnabled {", MAIN)
    for value in (
      'Button("Clear History…", role: .destructive)',
      'showClearHistoryConfirmation = true',
      '.confirmationDialog(',
      'Button("Clear History", role: .destructive)',
      'Button("Cancel", role: .cancel)',
      'switch ClearScanHistoryStore.clear()',
      'clearHistoryResultMessage = "Saved scan history was cleared."',
      'recentScanHistory = .empty',
      'recentScanHistory = .unavailable',
      'showClearHistoryResult = true',
      'accessibilityIdentifier("clearScanHistoryButton")',
    ):
      self.assertIn(value, PAGE)
    self.assertEqual(PAGE.count("ClearScanHistoryStore.clear()"), 1)
    self.assertNotIn(".onAppear", PAGE)
    self.assertNotIn("UserDefaults", PAGE)
    self.assertNotIn("FileManager", PAGE)
    self.assertNotIn("Process(", PAGE)
    self.assertNotIn("clamscan(", PAGE)

  def test_deletes_only_private_store_and_sqlite_sidecars(self):
    for value in (
      'databaseURL: URL = RecentScanHistoryReader.defaultDatabaseURL',
      'databaseURL.lastPathComponent == "scan-history.sqlite3"',
      'databaseURL.deletingLastPathComponent().lastPathComponent == "scan-history"',
      'original.st_dev', 'original.st_ino',
      'O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC',
      'O_RDONLY | O_NOFOLLOW | O_CLOEXEC',
      'AT_SYMLINK_NOFOLLOW', 'isPrivateRegularFile(pinned)',
      'current.st_dev == entry.device && current.st_ino == entry.inode',
      'unlinkat(directoryFD, $0, 0)', 'fsync(directoryFD)',
      '"scan-history.sqlite3-wal"', '"scan-history.sqlite3-shm"',
      '"scan-history.sqlite3-journal"', 'return .nothingToClear',
      'return .unavailable',
    ):
      self.assertIn(value, DELETE)
    for forbidden in (
      'removeItem(', 'removeItemAt(', 'removeItem(at:', 'removeAll(',
      'UserDefaults', 'NSWorkspace', 'Process(', 'PDFDocument',
      'scan-progress', 'clean-scan', 'scan-results',
      'launchServices', 'clamscan(',
    ):
      self.assertNotIn(forbidden, DELETE)
    self.assertIn("SQLITE_OPEN_READONLY", READER)

  def test_xcode_and_ci_run_real_tests(self):
    self.assertEqual(PROJECT.count('path = ClearScanHistory.swift;'), 1)
    self.assertIn('B21400000000000000000001', PROJECT)
    self.assertIn('B21400000000000000000002', PROJECT)
    self.assertIn('tests/scan/clear-history-action.py -v', CI)
    self.assertIn('test-clear-scan-history.swift -lsqlite3', CI)
    self.assertIn('PDFMagicOpenerApp/ClearScanHistory.swift', CI)
    self.assertIn('macos-build:', CI)
    self.assertIn('scanner-tests:', CI)

if __name__ == "__main__":
  unittest.main()
