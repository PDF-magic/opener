#!/usr/bin/env python3
"""Regression: browser-private and unknown contexts must never write history."""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scan_history_metadata import (
    BrowserScanContext, store_browser_scan_metadata, store_scan_metadata,
)
from scan_results import ScanResultStatus

ROOT = Path(__file__).resolve().parents[2]


class PrivateBrowsingHistoryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder = Path(temp.name) / "scan-history"
        self.database = self.folder / "scan-history.sqlite3"
        self.record = {
            "scanned_at": 1793448000.0,
            "final_status": ScanResultStatus.clean,
            "scanner_version": "1.5.0",
            "database_path": self.database,
        }

    def rows(self):
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                "SELECT scanned_at, final_status, scanner_version, "
                "protection_profile_id FROM scan_history ORDER BY id"
            ).fetchall()

    def test_missing_context_or_opt_in_never_creates_files_or_directories(self):
        cases = (
            {}, {"history_enabled": True},
            {"browsing_context": BrowserScanContext.UNKNOWN, "history_enabled": True},
            {"browsing_context": BrowserScanContext.PRIVATE, "history_enabled": True},
            {"browsing_context": BrowserScanContext.REGULAR},
            {"browsing_context": BrowserScanContext.REGULAR, "history_enabled": False},
            {"browsing_context": BrowserScanContext.REGULAR, "history_enabled": 1},
            {"browsing_context": "regular", "history_enabled": True},
            {"browsing_context": False, "history_enabled": True},
            {"browsing_context": None, "history_enabled": True},
            {"browsing_context": object(), "history_enabled": True},
        )
        for options in cases:
            with self.subTest(options=options):
                self.assertIs(store_browser_scan_metadata(**self.record, **options), False)
                self.assertFalse(self.folder.exists())
                self.assertFalse(self.database.exists())

    def test_private_and_unknown_do_not_modify_existing_history_even_with_opt_in(self):
        store_scan_metadata(**self.record)  # Synthetic regular metadata only.
        original_rows = self.rows()
        original_bytes = self.database.read_bytes()
        for context in (BrowserScanContext.PRIVATE, BrowserScanContext.UNKNOWN,
                        None, "regular", "private"):
            with self.subTest(context=context):
                self.assertIs(
                    store_browser_scan_metadata(
                        **self.record, browsing_context=context, history_enabled=True
                    ), False,
                )
                self.assertEqual(self.rows(), original_rows)
                self.assertEqual(self.database.read_bytes(), original_bytes)

    def test_private_browsing_is_denied_even_when_metadata_is_invalid(self):
        # Fail closed before touching disk, even if private-session input is
        # malformed or an existing directory is not writable.
        invalid = {**self.record, "final_status": "clean"}
        self.assertIs(store_browser_scan_metadata(
            **invalid, browsing_context=BrowserScanContext.PRIVATE,
            history_enabled=True
        ), False)
        self.assertFalse(self.folder.exists())

    def test_verified_regular_context_and_explicit_opt_in_can_append_metadata(self):
        self.assertIs(store_browser_scan_metadata(
            **self.record, browsing_context=BrowserScanContext.REGULAR,
            history_enabled=True
        ), True)
        self.assertEqual(self.rows(), [(1793448000.0, "clean", "1.5.0", "built-in")])
        with sqlite3.connect(self.database) as connection:
            columns = [row[1] for row in connection.execute(
                "PRAGMA table_xinfo(scan_history)"
            )]
        self.assertEqual(columns, ["id", "scanned_at", "final_status",
                                   "scanner_version", "protection_profile_id"])

    def test_browser_integration_is_inactive_and_private_access_excluded(self):
        root = ROOT / "extensions"
        for manifest in ("webextension/manifest.json", "safari/manifest.json"):
            data = json.loads((root / manifest).read_text(encoding="utf-8"))
            self.assertEqual(data["incognito"], "not_allowed")
        worker = (root / "webextension/src/background.js").read_text()
        self.assertEqual(worker,
            "// Inactive shared WebExtensions background entry point.\n"
            "// Do not listen for messages, inspect PDFs or request native access here.\n"
            "void 0;\n")
        gate = (root / "webextension/src/private-browsing-consent.js").read_text()
        self.assertIn("let status = \"consent-required\"", gate)
        self.assertIn("canProcessPrivateData", gate)
        # Consent to a private session never supplies history-write consent.
        writer = (ROOT / "scan_history_metadata.py").read_text()
        self.assertIn("browsing_context is not BrowserScanContext.REGULAR", writer)
        self.assertIn("history_enabled is not True", writer)
        self.assertNotIn("store_browser_scan_metadata", worker)


if __name__ == "__main__":
    unittest.main()
