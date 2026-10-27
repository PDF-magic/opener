#!/usr/bin/env python3
"""Contract tests for section 1.3 scan result status definitions."""

import json
import unittest

from scan_results import ScanResultStatus


class ScanResultContractTests(unittest.TestCase):
    EXPECTED = (
        "clean",
        "malwareDetected",
        "suspiciousStructure",
        "encrypted",
        "incompleteScan",
        "scanFailed",
        "scanTimedOut",
        "fileChanged",
        "fileTooLarge",
        "cancelled",
    )

    def test_exact_ten_distinct_result_names(self):
        self.assertEqual(tuple(status.value for status in ScanResultStatus), self.EXPECTED)
        self.assertEqual(len(set(self.EXPECTED)), 10)
        for name in self.EXPECTED:
            with self.subTest(name=name):
                self.assertIs(ScanResultStatus(name), getattr(ScanResultStatus, name))

    def test_statuses_round_trip_as_json_strings(self):
        for status in ScanResultStatus:
            with self.subTest(status=status.value):
                self.assertEqual(json.loads(json.dumps(status)), status.value)
                self.assertIs(ScanResultStatus(json.loads(json.dumps(status))), status)

    def test_only_clean_permits_open(self):
        for status in ScanResultStatus:
            with self.subTest(status=status.value):
                self.assertIs(status.permits_open, status is ScanResultStatus.clean)

    def test_unknown_or_ambiguous_outcomes_not_accepted(self):
        for invalid in ("", "unknown", "Clean", "malware", "scanFailed "):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    ScanResultStatus(invalid)


if __name__ == "__main__":
    unittest.main()
