#!/usr/bin/env python3
"""Contract tests for section 1.3 scan result status definitions."""

import json
import unittest

from scan_results import ScanResult, ScanResultStatus


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

    def test_found_lines_attach_unique_detection_names_without_paths(self):
        output = (
            "/tmp/private: alias.pdf: Eicar-Test-Signature FOUND\n"
            "/tmp/archive/child.pdf: Win.Trojan.Agent-123 FOUND\n"
            "/tmp/private: alias.pdf: Eicar-Test-Signature FOUND\n"
            "/tmp/archive/child.pdf: OK\n"
        )
        result = ScanResult.from_clamav_output(output)
        self.assertEqual(result.detection_names,
                         ("Eicar-Test-Signature", "Win.Trojan.Agent-123"))
        self.assertIsInstance(result.detection_names, tuple)

    def test_diagnostics_cannot_be_recorded_as_detection_names(self):
        output = (
            "/tmp/secret.pdf: OK\n"
            "/tmp/secret.pdf: Empty file\n"
            "/tmp/secret.pdf: ../../private/source FOUND\n"
            "/tmp/secret.pdf:  FOUND\n"
            "/tmp/secret.pdf: Win.Agent FOUND ignored\n"
            "Not a ClamAV signature FOUND\n"
        )
        self.assertEqual(ScanResult.from_clamav_output(output).detection_names, ())
        self.assertEqual(ScanResult().detection_names, ())

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
