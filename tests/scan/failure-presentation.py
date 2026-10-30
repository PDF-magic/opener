#!/usr/bin/env python3
"""Verify scanner errors do not masquerade as confirmed malware detections."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("scan_error_presentation", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


def output(code, stdout="", stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class ScanFailurePresentationTests(unittest.TestCase):
    def test_only_confirmed_signature_is_labeled_malware(self):
        verdict = opener.decide_opening(opener.capture_detection(
            output(1, "/private/report.pdf: Eicar-Test-Signature FOUND")))
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, "Malware was detected; opening was stopped.")
        self.assertEqual(verdict.detection_names, ("Eicar-Test-Signature",))
        self.assertNotIn("/private", verdict.reason)

    def test_scanner_errors_remain_generic_even_with_found_output(self):
        cases = (
            output(1, "", "Unable to read /private/report.pdf"),
            output(1, "/private/report.pdf: OK"),
            output(1, "/private/report.pdf: ERROR"),
            output(1, "/private/report.pdf: Eicar-Test-Signature FOUND", "scanner failed"),
            output(2, "/private/report.pdf: Eicar-Test-Signature FOUND", "scanner failed"),
            output(2, "", "File access denied"),
            output(-9, "", ""),
            output(0, "/private/report.pdf: OK", "WARNING: partial scan"),
            output(0, "/private/report.pdf: Empty file"),
        )
        for scan in cases:
            with self.subTest(exit_code=scan.returncode, stdout=scan.stdout, stderr=scan.stderr):
                decision = opener.decide_opening(opener.capture_detection(scan))
                self.assertFalse(decision.allowed)
                self.assertNotIn("Malware was detected", decision.reason)
                self.assertNotIn("/private", decision.reason)
                self.assertIn("opening was stopped", decision.reason)
                self.assertEqual(opener.safe_scan_failure(RuntimeError(decision.reason)), decision.reason)

    def test_heuristics_are_not_malware(self):
        for signature in ("Heuristics.Limits.Exceeded.MaxFileSize",
                          "Heuristics.Encrypted.PDF",
                          "Heuristics.OLE2.ContainsMacros"):
            with self.subTest(signature=signature):
                decision = opener.decide_opening(opener.capture_detection(
                    output(1, "/private/report.pdf: " + signature + " FOUND")))
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason,
                    "The scanner flagged a suspicious or unscannable item; opening was stopped.")
                self.assertEqual(decision.detection_names, (signature,))

    def test_no_verified_signature_never_claims_malware(self):
        for raw in ("file: FOUND", "file: ../../private FOUND",
                    "file: Malware FOUND ignored", ""):
            decision = opener.decide_opening(opener.capture_detection(output(1, raw)))
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason, "The malware scan could not finish; opening was stopped.")

    def test_all_rejected_outcomes_preserve_quarantine_and_never_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            document = Path(directory) / "sample.pdf"
            original = b"%PDF-1.4\nSample\n"
            document.write_bytes(original)
            failures = (
                output(1, "file: Eicar-Test-Signature FOUND"),
                output(1, "", "Permission denied"),
                output(1, "file: Heuristics.Encrypted.PDF FOUND"),
                output(2, "file: Eicar-Test-Signature FOUND", "Scanner error"),
                output(0, "file: OK", "incomplete"),
            )
            for scan in failures:
                with self.subTest(scan=scan), \
                     patch.object(opener, "CACHE_DB", Path(directory) / "cache.sqlite3"), \
                     patch.object(opener, "intended_destination", return_value="com.brave.Browser"), \
                     patch.object(opener, "pdf_fallback_application", return_value=None), \
                     patch.object(opener, "record_scan_destination"), \
                     patch.object(opener, "verify_launch_target"), \
                     patch.object(opener, "verify_local_file_available"), \
                     patch.object(opener, "read_signature_database_version", return_value=None), \
                     patch.object(opener, "run_scan_command", return_value=scan), \
                     patch.object(opener, "remove_quarantine") as unquarantine, \
                     patch.object(opener, "launch_clean_file") as launch:
                    with self.assertRaises(RuntimeError) as error:
                        opener.scan_and_open(str(document), "/scanner")
                    self.assertNotIn(str(document), str(error.exception))
                    unquarantine.assert_not_called()
                    launch.assert_not_called()
                    self.assertEqual(document.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
