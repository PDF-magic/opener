#!/usr/bin/env python3
"""Regression tests for path-free, private optional scan history metadata."""

from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest

from scan_history_metadata import ScanHistoryStorageError, store_scan_metadata
from scan_results import EFFECTIVE_POLICY_ID, ScanResultStatus


class ScanHistoryMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "private"
        self.database = self.folder / "history.sqlite3"

    def store(self, status=ScanResultStatus.clean, **kwargs):
        return store_scan_metadata(scanned_at=1_783_000_123.125,
                                   final_status=status, database_path=self.database,
                                   **kwargs)

    def records(self):
        with sqlite3.connect(self.database) as connection:
            return connection.execute(
                "SELECT scanned_at, final_status, scanner_version, "
                "protection_profile_id FROM scan_history ORDER BY id"
            ).fetchall()

    def test_all_terminal_statuses_and_timestamps_round_trip(self):
        self.assertFalse(self.database.exists())
        for status in ScanResultStatus:
            self.store(status)
        self.assertEqual(
            self.records(),
            [(1_783_000_123.125, status.value, None, EFFECTIVE_POLICY_ID)
             for status in ScanResultStatus],
        )

    def test_scanner_versions_and_unknown_values(self):
        self.store(scanner_version="1.4.3")
        self.store(ScanResultStatus.scanFailed)
        self.store(ScanResultStatus.incompleteScan, scanner_version="1.5.0")
        self.assertEqual([entry[2] for entry in self.records()],
                         ["1.4.3", None, "1.5.0"])

    def test_private_permissions_and_exact_path_free_schema(self):
        self.store(ScanResultStatus.malwareDetected, scanner_version="1.4.3")
        self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.database.stat().st_mode), 0o600)
        with sqlite3.connect(self.database) as connection:
            columns = [row[1] for row in connection.execute("PRAGMA table_info(scan_history)")]
        self.assertEqual(columns, ["id", "scanned_at", "final_status",
                                   "scanner_version", "protection_profile_id"])

    def test_reject_untrusted_status_version_time_and_inactive_tier(self):
        cases = (
            {"final_status": "clean"}, {"final_status": None},
            {"scanned_at": float("nan")}, {"scanned_at": float("inf")},
            {"scanned_at": -1}, {"scanned_at": True},
            {"scanner_version": "/private/document.pdf"},
            {"scanner_version": "ClamAV 1.4.3"},
            {"scanner_version": "1.4.3\n/path"},
            {"scanner_version": ""},
            {"protection_profile_id": "enhanced"},
            {"protection_profile_id": "standard"},
            {"protection_profile_id": "maximum"},
            {"protection_profile_id": "../private"},
        )
        for change in cases:
            with self.subTest(change=change):
                values = {"scanned_at": 1_783_000_123.125,
                          "final_status": ScanResultStatus.clean,
                          "scanner_version": None,
                          "protection_profile_id": EFFECTIVE_POLICY_ID,
                          "database_path": self.database}
                values.update(change)
                with self.assertRaises(ValueError):
                    store_scan_metadata(**values)
                self.assertFalse(self.database.exists())

    def test_symlink_database_and_directory_do_not_touch_target(self):
        target = Path(self.temp.name) / "unrelated"
        target.write_text("unmodified")
        self.folder.mkdir(mode=0o700)
        self.database.symlink_to(target)
        with self.assertRaises(ScanHistoryStorageError):
            self.store()
        self.assertEqual(target.read_text(), "unmodified")
        self.database.unlink()
        self.folder.rmdir()
        self.folder.symlink_to(Path(self.temp.name), target_is_directory=True)
        with self.assertRaises(ScanHistoryStorageError):
            self.store()
        self.assertEqual(target.read_text(), "unmodified")

    def test_existing_nonprivate_directory_not_modified(self):
        self.folder.mkdir(mode=0o755)
        with self.assertRaises(ScanHistoryStorageError):
            self.store()
        self.assertEqual(stat.S_IMODE(self.folder.stat().st_mode), 0o755)
        self.assertFalse(self.database.exists())

    def test_corrupt_history_store_does_not_give_clean_verdict(self):
        self.folder.mkdir(mode=0o700)
        self.database.write_text("not a database")
        with self.assertRaises(ScanHistoryStorageError):
            self.store()
        self.assertEqual(self.database.read_text(), "not a database")


if __name__ == "__main__":
    unittest.main()
