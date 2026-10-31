#!/usr/bin/env python3
"""Privacy regressions for the optional, metadata-only local history format."""

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from scan_history_metadata import ScanHistoryStorageError, store_scan_metadata
from scan_history_record import ScanHistoryRecord, ScanHistorySource
from scan_results import ScanResultStatus


# Synthetic fixtures only; never read PDFs, users' browsing records, or files.
FORBIDDEN = {
    "pdf_contents": "%PDF-1.7 UNIQUE_PRIVATE_BODY_MARKER",
    "document_text": "UNIQUE_PRIVATE_EXTRACTED_TEXT",
    "embedded_attachments": ["UNIQUE_PRIVATE_ATTACHMENT_BYTES"],
    "browsing_history": ["https://example.invalid/private/visited"],
    "source_url": "https://example.invalid/private/source.pdf?token=PRIVATE",
}
COLUMNS = ("id", "scanned_at", "final_status", "scanner_version",
           "protection_profile_id")


class ScanHistoryPrivacyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name) / "private"
        self.database = self.folder / "scan-history.sqlite3"

    def save(self):
        store_scan_metadata(
            scanned_at=1793448000,
            final_status=ScanResultStatus.scanFailed,
            scanner_version="1.5.0",
            database_path=self.database,
        )

    def test_serialized_records_reject_all_forbidden_fields(self):
        record = ScanHistoryRecord(
            timestamp=1793448000,
            status=ScanResultStatus.scanFailed,
            source=ScanHistorySource.browser,
        )
        allowed = {"schema_version", "timestamp", "status", "source", "filename", "opened"}
        encoded = record.to_dict()
        self.assertEqual(set(encoded), allowed)
        self.assertEqual(encoded["source"], "browser")  # Category, not visited pages.
        self.assertIsNone(encoded["filename"])
        dumped = json.dumps(encoded)
        for name, value in FORBIDDEN.items():
            with self.subTest(field=name):
                self.assertNotIn(name, dumped)
                self.assertNotIn(str(value), dumped)
                with self.assertRaises(ValueError):
                    ScanHistoryRecord.from_dict({**encoded, name: value})

    def test_storage_api_rejects_raw_private_payloads(self):
        for name, value in FORBIDDEN.items():
            with self.subTest(field=name):
                with self.assertRaises(TypeError):
                    store_scan_metadata(
                        scanned_at=1793448000,
                        final_status=ScanResultStatus.clean,
                        database_path=self.database,
                        **{name: value},
                    )
                self.assertFalse(self.database.exists())

    def test_disk_stores_only_canonical_metadata_and_no_payload(self):
        self.save()
        with sqlite3.connect(self.database) as connection:
            columns = tuple(row[1] for row in connection.execute(
                "PRAGMA table_xinfo(scan_history)"
            ))
            values = connection.execute(
                "SELECT scanned_at, final_status, scanner_version, "
                "protection_profile_id FROM scan_history"
            ).fetchall()
        self.assertEqual(columns, COLUMNS)
        self.assertEqual(values, [(1793448000.0, "scanFailed", "1.5.0", "built-in")])
        db_bytes = self.database.read_bytes()
        for name, value in FORBIDDEN.items():
            with self.subTest(field=name):
                self.assertNotIn(name.encode("utf-8"), db_bytes)
                self.assertNotIn(str(value).encode("utf-8"), db_bytes)

    def test_refuses_any_extra_sensitive_column_in_existing_history(self):
        for forbidden in FORBIDDEN:
            with self.subTest(column=forbidden):
                self.folder.mkdir(mode=0o700, exist_ok=True)
                with sqlite3.connect(self.database) as connection:
                    connection.execute(
                        "CREATE TABLE scan_history (id INTEGER PRIMARY KEY, "
                        "scanned_at REAL NOT NULL, final_status TEXT NOT NULL, "
                        "scanner_version TEXT, protection_profile_id TEXT NOT NULL, "
                        + forbidden + " TEXT)"
                    )
                with self.assertRaises(ScanHistoryStorageError):
                    self.save()
                with sqlite3.connect(self.database) as connection:
                    count = connection.execute("SELECT COUNT(*) FROM scan_history").fetchone()[0]
                self.assertEqual(count, 0)
                self.database.unlink()

    def test_refuses_hidden_generated_content_column(self):
        self.folder.mkdir(mode=0o700)
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE scan_history (id INTEGER PRIMARY KEY, "
                "scanned_at REAL NOT NULL, final_status TEXT NOT NULL, "
                "scanner_version TEXT, protection_profile_id TEXT NOT NULL, "
                "document_text TEXT GENERATED ALWAYS AS (final_status) VIRTUAL)"
            )
        with self.assertRaises(ScanHistoryStorageError):
            self.save()
        with sqlite3.connect(self.database) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM scan_history").fetchone()[0], 0
            )


if __name__ == "__main__":
    unittest.main()
