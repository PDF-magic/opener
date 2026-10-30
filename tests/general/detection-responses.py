#!/usr/bin/env python3
"""Complete, fail-closed response contract for each scan-result status."""

from dataclasses import FrozenInstanceError
import unittest

from detection_responses import (
    DetectionAction, DetectionResponse, response_for_detection,
)
from scan_results import ScanResultStatus


class DetectionResponseTests(unittest.TestCase):
    def test_every_canonical_status_has_its_intended_response(self):
        expected = {
            ScanResultStatus.clean: DetectionAction.VERIFY_BEFORE_HANDOFF,
            ScanResultStatus.malwareDetected: DetectionAction.DENY_OPEN,
            ScanResultStatus.suspiciousStructure: DetectionAction.DENY_OPEN,
            ScanResultStatus.encrypted: DetectionAction.DENY_OPEN,
            ScanResultStatus.incompleteScan: DetectionAction.DENY_OPEN,
            ScanResultStatus.scanFailed: DetectionAction.DENY_OPEN,
            ScanResultStatus.scanTimedOut: DetectionAction.DENY_OPEN,
            ScanResultStatus.fileChanged: DetectionAction.DENY_OPEN,
            ScanResultStatus.fileTooLarge: DetectionAction.DENY_OPEN,
            ScanResultStatus.cancelled: DetectionAction.STOP_CANCELLED,
        }
        self.assertEqual(len(expected), len(ScanResultStatus))
        for status in ScanResultStatus:
            with self.subTest(status=status.value):
                response = response_for_detection(status)
                self.assertIsInstance(response, DetectionResponse)
                self.assertEqual(response.action, expected[status])
                self.assertTrue(response.preserve_quarantine)
                self.assertTrue(response.user_message.strip())
                self.assertNotIn("/", response.user_message)
                self.assertNotIn("\\", response.user_message)
                self.assertEqual(
                    response.show_failure_alert,
                    status not in (ScanResultStatus.clean, ScanResultStatus.cancelled),
                )
                self.assertIs(response, response_for_detection(status))

    def test_only_clean_can_continue_to_independent_safety_gates(self):
        for status in ScanResultStatus:
            with self.subTest(status=status.value):
                self.assertEqual(
                    response_for_detection(status).action
                    is DetectionAction.VERIFY_BEFORE_HANDOFF,
                    status is ScanResultStatus.clean,
                )
                self.assertIs(status.permits_open, status is ScanResultStatus.clean)
        self.assertNotIn("open", [action.value for action in DetectionAction])

    def test_non_malware_outcomes_are_never_mislabeled_as_confirmed_malware(self):
        for status in ScanResultStatus:
            if status is ScanResultStatus.malwareDetected:
                self.assertIn("Malware was detected", response_for_detection(status).user_message)
            else:
                self.assertNotIn("Malware was detected", response_for_detection(status).user_message)

    def test_unknown_values_must_not_be_interpreted_as_clean(self):
        for untrusted in (
            "clean", "Clean", "", "malwareDetected", None, 0, True,
            object(), {"status": "clean"},
        ):
            with self.subTest(untrusted=repr(untrusted)):
                response = response_for_detection(untrusted)
                self.assertIs(response.action, DetectionAction.DENY_OPEN)
                self.assertTrue(response.preserve_quarantine)
                self.assertTrue(response.show_failure_alert)
                self.assertIn("could not be verified", response.user_message)

    def test_responses_cannot_be_mutated(self):
        response = response_for_detection(ScanResultStatus.malwareDetected)
        with self.assertRaises(FrozenInstanceError):
            response.action = DetectionAction.VERIFY_BEFORE_HANDOFF
        with self.assertRaises(FrozenInstanceError):
            response.preserve_quarantine = False
        with self.assertRaises(FrozenInstanceError):
            response.show_failure_alert = False

    def test_policy_definitions_do_not_launch_or_change_scanning(self):
        from pathlib import Path
        src = (Path(__file__).resolve().parents[2] / "detection_responses.py").read_text()
        self.assertNotIn("subprocess", src)
        self.assertNotIn("os.system", src)
        self.assertNotIn("launch_clean_file", src)
        self.assertNotIn("remove_quarantine", src)
        self.assertNotIn("scan-and-open.py", src)
        self.assertNotIn("UserDefaults", src)


if __name__ == "__main__":
    unittest.main()
