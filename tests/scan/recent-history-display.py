#!/usr/bin/env python3
"""Guard on-demand recent-result display against collection and unsafe data."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODEL = (ROOT / "PDFMagicOpenerApp/RecentScanHistory.swift").read_text()
PAGE = (ROOT / "PDFMagicOpenerApp/ScanHistorySettingsView.swift").read_text()
MAIN = (ROOT / "PDFMagicOpenerApp/MainPreferencesView.swift").read_text()
PROJECT = (ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()

class RecentScanHistoryDisplayTests(unittest.TestCase):
    def test_explicit_action_only_and_accessible_outcomes(self):
        self.assertIn('GroupBox("History availability")', PAGE)
        self.assertIn("init(scanHistoryEnabled: Bool = false)", MAIN)
        self.assertIn("if section != .scanHistory || scanHistoryEnabled {", MAIN)
        self.assertIn('Button("Show recent scan results")', PAGE)
        self.assertIn('recentScanHistory = RecentScanHistoryReader.load()', PAGE)
        self.assertIn('accessibilityIdentifier("recentScanHistoryResults")', PAGE)
        self.assertIn('accessibilityIdentifier("recentScanHistoryEmptyState")', PAGE)
        self.assertIn('accessibilityIdentifier("recentScanHistoryUnavailableState")', PAGE)
        self.assertNotIn(".onAppear", PAGE)
        self.assertIn("ForEach(rows)", PAGE)
        self.assertIn('row.statusLabel', PAGE)
        self.assertIn('row.scannedAt.formatted(', PAGE)
        self.assertNotIn('row.filename', PAGE)
        self.assertIn("Automatic history collection remains off", PAGE)
        self.assertIn("independently verify the user's opt-in", PAGE)

    def test_exact_private_schema_read_only_and_bounded(self):
        self.assertIn('SQLITE_OPEN_READONLY', MODEL)
        self.assertIn('SQLITE_OPEN_NOFOLLOW', MODEL)
        self.assertIn('databaseURL.deletingLastPathComponent().resolvingSymlinksInPath()', MODEL)
        self.assertIn('isPrivate(resolvedDatabase.path, directory: false) == true', MODEL)
        self.assertIn('sqlite3_db_readonly(database, "main") == 1', MODEL)
        self.assertIn('hasExactSchema(database)', MODEL)
        self.assertIn('lstat(path, &metadata)', MODEL)
        self.assertIn('metadata.st_uid == getuid()', MODEL)
        self.assertIn('SQLITE_OPEN_FULLMUTEX', MODEL)
        self.assertIn('LIMIT 20', MODEL)
        self.assertIn('ORDER BY scanned_at DESC, id DESC', MODEL)
        self.assertIn('return rows.isEmpty ? .empty : .entries(rows)', MODEL)
        self.assertIn('case "clean": return "Clean scan (opening not verified)"', MODEL)
        self.assertIn('status: status, scannerVersion: version, profile: profile', MODEL)
        query = MODEL.split('let sql = ', 1)[1].split('guard sqlite3_prepare_v2', 1)[0]
        for forbidden in ('filename', 'document_text', 'source_url', 'pdf_contents',
                          'browsing_history', 'attachments'):
            self.assertNotIn(forbidden, query)
        for forbidden in ('INSERT INTO', 'CREATE TABLE', 'ALTER TABLE',
                          'UPDATE scan_history', 'DELETE FROM scan_history',
                          'Process(', 'URLSession'):
            self.assertNotIn(forbidden, MODEL)

    def test_xcode_and_ci_compile_and_test_real_reader(self):
        self.assertEqual(PROJECT.count('path = RecentScanHistory.swift;'), 1)
        self.assertIn('B21200000000000000000001', PROJECT)
        self.assertIn('B21200000000000000000002', PROJECT)
        self.assertIn('tests/scan/recent-history-display.py -v', CI)
        self.assertIn('test-recent-scan-history.swift -lsqlite3', CI)
        self.assertIn('macos-build:', CI)

if __name__ == "__main__":
    unittest.main()
