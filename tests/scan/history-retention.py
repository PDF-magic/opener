#!/usr/bin/env python3
"""Configured retention and automatic expiry for optional private history."""
import json
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest import mock

from scan_history_metadata import (
    RETENTION_ALLOWED_DAYS, RETENTION_DEFAULT_DAYS, ScanHistoryStorageError,
    prune_expired_history, store_scan_metadata,
)
from scan_results import ScanResultStatus


class HistoryRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "scan-history"
        self.db = self.folder / "scan-history.sqlite3"
        self.config = self.folder / "retention.json"
        self.now = 1_800_000_000.0
        self.clock = mock.patch("scan_history_metadata.time.time", return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)

    def save_policy(self, days):
        self.folder.mkdir(mode=0o700, exist_ok=True)
        self.config.write_text(json.dumps({"retention_days": days}))
        self.config.chmod(0o600)

    def store(self, at):
        store_scan_metadata(
            database_path=self.db, scanned_at=at,
            final_status=ScanResultStatus.clean, scanner_version="1.5.0",
        )

    def timestamps(self):
        with sqlite3.connect(self.db) as connection:
            return [row[0] for row in connection.execute(
                "SELECT scanned_at FROM scan_history ORDER BY scanned_at"
            )]

    def test_default_and_all_allowed_choices_expire_on_append(self):
        self.assertEqual(RETENTION_DEFAULT_DAYS, 30)
        self.assertEqual(RETENTION_ALLOWED_DAYS, (7, 30, 90, 365))
        for days in RETENTION_ALLOWED_DAYS:
            with self.subTest(days=days):
                self.save_policy(days)
                self.store(self.now - days * 86400 - 0.5)
                self.assertEqual(self.timestamps(), [])
                self.store(self.now - days * 86400)
                self.store(self.now + 5)
                self.assertEqual(self.timestamps(),
                                 [self.now - days * 86400, self.now + 5])
                self.db.unlink()

    def test_missing_setting_defaults_and_does_not_enable_history(self):
        self.assertEqual(prune_expired_history(database_path=self.db, now=self.now), 0)
        self.assertFalse(self.db.exists())
        self.assertFalse(self.folder.exists())
        self.store(self.now - 31 * 86400)
        self.assertEqual(self.timestamps(), [])
        self.store(self.now - 29 * 86400)
        self.assertEqual(len(self.timestamps()), 1)
        self.assertFalse(self.config.exists())

    def test_shortening_retention_prunes_existing_rows_automatically(self):
        self.save_policy(365)
        for age in (200, 80, 15, 1):
            self.store(self.now - age * 86400)
        self.assertEqual(len(self.timestamps()), 4)
        self.save_policy(30)
        self.store(self.now)
        self.assertEqual(len(self.timestamps()), 3)
        self.save_policy(7)
        self.assertEqual(prune_expired_history(database_path=self.db, now=self.now), 1)
        self.assertEqual(self.timestamps(), [self.now - 1 * 86400, self.now])
        self.assertEqual(prune_expired_history(database_path=self.db, now=self.now), 0)

    def test_reject_unsafe_or_malformed_preferences_without_expiring_data(self):
        self.save_policy(365)
        self.store(self.now - 100 * 86400)
        previous = self.timestamps()
        for bad in (True, 0, -1, 8, 1000, "30", 30.5, None, {"days": 30}):
            self.save_policy(bad)
            with self.subTest(bad=bad):
                with self.assertRaises(ScanHistoryStorageError):
                    self.store(self.now)
                self.assertEqual(self.timestamps(), previous)
        self.save_policy(30)
        self.config.chmod(0o644)
        with self.assertRaises(ScanHistoryStorageError):
            prune_expired_history(database_path=self.db, now=self.now)
        self.assertEqual(self.timestamps(), previous)
        self.config.chmod(0o600)
        self.config.unlink()
        outside = self.root / "not-history"
        outside.write_text('{"retention_days": 7}')
        self.config.symlink_to(outside)
        with self.assertRaises(ScanHistoryStorageError):
            self.store(self.now)
        self.assertEqual(self.timestamps(), previous)
        self.assertEqual(outside.read_text(), '{"retention_days": 7}')

    def test_symlink_database_and_nonprivate_folder_refuse_cleanup(self):
        self.save_policy(30)
        outside = self.root / "outside"
        outside.write_text("unmodified")
        self.db.symlink_to(outside)
        with self.assertRaises(ScanHistoryStorageError):
            prune_expired_history(database_path=self.db, now=self.now)
        self.assertEqual(outside.read_text(), "unmodified")
        self.db.unlink()
        self.folder.chmod(0o755)
        with self.assertRaises(ScanHistoryStorageError):
            prune_expired_history(database_path=self.db, now=self.now)
        self.assertFalse(self.db.exists())

    def test_unrelated_cache_and_schema_are_never_touched(self):
        self.save_policy(7)
        cache = self.root / "clean-scan-cache"
        cache.write_text("unaltered")
        self.store(self.now - 10 * 86400)
        self.assertEqual(self.timestamps(), [])
        self.assertEqual(cache.read_text(), "unaltered")
        with sqlite3.connect(self.db) as connection:
            connection.execute("ALTER TABLE scan_history ADD COLUMN source_url TEXT")
        with self.assertRaises(ScanHistoryStorageError):
            prune_expired_history(database_path=self.db, now=self.now)
        self.assertEqual(cache.read_text(), "unaltered")


if __name__ == "__main__":
    unittest.main()
