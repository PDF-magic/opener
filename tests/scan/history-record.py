#!/usr/bin/env python3
"""Contract tests for section 14.3's passive local history format."""

from dataclasses import FrozenInstanceError
import json
import unittest

from scan_history_record import HISTORY_SCHEMA_VERSION, ScanHistoryRecord, ScanHistorySource
from scan_results import ScanResultStatus


class ScanHistoryRecordTests(unittest.TestCase):
    def sample(self):
        return ScanHistoryRecord(timestamp=1793448000, status=ScanResultStatus.clean)

    def test_minimal_record_has_explicit_unknowns_and_no_sensitive_fields(self):
        record = self.sample()
        self.assertEqual(HISTORY_SCHEMA_VERSION, 1)
        self.assertEqual(record.to_dict(), {
            "schema_version": 1,
            "timestamp": 1793448000,
            "status": "clean",
            "source": "unknown",
            "filename": None,
            "opened": None,
        })
        self.assertIsNone(record.opened)  # A clean scan cannot prove opening.
        self.assertNotIn("path", json.dumps(record.to_dict()))

    def test_round_trip_uses_canonical_scan_statuses_and_sources(self):
        for status in ScanResultStatus:
            for source in ScanHistorySource:
                with self.subTest(status=status, source=source):
                    record = ScanHistoryRecord(
                        timestamp=0, status=status, source=source,
                        filename="report.pdf", opened=False,
                    )
                    encoded = json.loads(json.dumps(record.to_dict()))
                    self.assertEqual(ScanHistoryRecord.from_dict(encoded), record)
                    self.assertFalse(record.opened)

    def test_opening_is_independent_of_clean_verdict(self):
        for status in ScanResultStatus:
            record = ScanHistoryRecord(timestamp=1, status=status, opened=None)
            self.assertIsNone(record.opened)
        self.assertTrue(ScanHistoryRecord(
            timestamp=1, status=ScanResultStatus.clean, opened=True
        ).opened)

    def test_rejects_paths_urls_controls_and_oversized_names(self):
        for filename in (
            "", ".", "..", "/private/document.pdf", "folder/document.pdf",
            "folder\\document.pdf", "https://example.com/private.pdf",
            "private\x00name.pdf", "secret\nfile.pdf", "secret\u202efile.pdf",
            "a" * 256,
        ):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                ScanHistoryRecord(timestamp=1, status=ScanResultStatus.clean, filename=filename)
        self.assertEqual(ScanHistoryRecord(
            timestamp=1, status=ScanResultStatus.clean, filename="Résumé.pdf"
        ).filename, "Résumé.pdf")

    def test_invalid_types_and_outcomes_are_rejected(self):
        for invalid_timestamp in (True, -1, 1.25, "1700000000", 2**53):
            with self.subTest(timestamp=invalid_timestamp), self.assertRaises(ValueError):
                ScanHistoryRecord(timestamp=invalid_timestamp, status=ScanResultStatus.clean)
        for invalid_opened in (0, 1, "true"):
            with self.subTest(opened=invalid_opened), self.assertRaises(ValueError):
                ScanHistoryRecord(timestamp=1, status=ScanResultStatus.clean, opened=invalid_opened)
        with self.assertRaises(ValueError):
            ScanHistoryRecord(timestamp=1, status="clean")
        with self.assertRaises(ValueError):
            ScanHistoryRecord(timestamp=1, status=ScanResultStatus.clean, source="browser")
        with self.assertRaises(FrozenInstanceError):
            self.sample().status = ScanResultStatus.scanFailed

    def test_rejects_unknown_versions_fields_and_fake_clean_status(self):
        good = self.sample().to_dict()
        cases = (
            {**good, "schema_version": 2},
            {**good, "schema_version": True},
            {**good, "status": "success"},
            {**good, "status": "Clean"},
            {**good, "source": "external-url"},
            {**good, "status": True},
            {**good, "opened": "yes"},
            {**good, "file_path": "/private/secret.pdf"},
            {key: value for key, value in good.items() if key != "opened"},
        )
        for value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                ScanHistoryRecord.from_dict(value)
        with self.assertRaises(ValueError):
            ScanHistoryRecord.from_dict([])


if __name__ == "__main__":
    unittest.main()
