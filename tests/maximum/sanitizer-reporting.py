#!/usr/bin/env python3
"""opener-0324: sanitizer crashes are not malware detections or clean results."""

from dataclasses import FrozenInstanceError
from io import BytesIO
from pathlib import Path
import os
import signal
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfWriter
from scan_results import ScanResultStatus
import maximum_sanitized_copy as copies


def valid_pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=180, height=220)
    data = BytesIO()
    writer.write(data)
    return data.getvalue()


class SanitizerReportingTests(unittest.TestCase):
    def test_failures_have_distinct_non_malware_category_and_no_verdict(self):
        for kind in copies.SanitizerFailureKind:
            with self.subTest(kind=kind):
                attempt = copies._failed(kind)
                self.assertIsNone(attempt.offer)
                self.assertEqual(attempt.failure.kind, kind)
                self.assertIs(attempt.permits_open, False)
                self.assertNotEqual(kind.value, ScanResultStatus.malwareDetected.value)
                record = attempt.failure.to_dict()
                self.assertEqual(record["status"], "sanitizerFailure")
                self.assertEqual(record["scanVerdict"], "notAssessed")
                self.assertIs(record["permitsOpen"], False)
                self.assertNotIn("detectionNames", record)
                self.assertNotIn("FOUND", attempt.failure.message)
                with self.assertRaises(FrozenInstanceError):
                    attempt.failure.kind = copies.SanitizerFailureKind.CRASHED

    def test_signal_crash_vs_nonzero_failure_are_distinct(self):
        data = valid_pdf()
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")):
            for code, expected in (
                (-signal.SIGKILL, copies.SanitizerFailureKind.CRASHED),
                (1, copies.SanitizerFailureKind.PROCESS_FAILED),
                (137, copies.SanitizerFailureKind.PROCESS_FAILED),
            ):
                with self.subTest(code=code), patch.object(
                    copies, "run_limited_converter",
                    return_value=subprocess.CompletedProcess([], code, b""),
                ):
                    report = copies.attempt_sanitized_pdf_copy(data)
                    self.assertEqual(report.failure.kind, expected)
                    self.assertIsNone(report.offer)
                    self.assertIsNone(copies.offer_sanitized_pdf_copy(data))

    def test_crash_is_observed_from_real_isolated_process(self):
        if os.name != "posix":
            self.skipTest("Real signal-based crash requires POSIX")
        with tempfile.TemporaryDirectory() as temp:
            worker = Path(temp) / "sanitizer-crash"
            worker.write_text("#!/bin/sh\nkill -KILL $$\n", encoding="ascii")
            worker.chmod(0o700)
            # Prove that the real executable dies from SIGKILL, independent
            # of sanitizer supervision's subsequent fail-closed cleanup.
            direct = subprocess.run(
                (str(worker),), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=3, check=False,
            )
            self.assertEqual(direct.returncode, -signal.SIGKILL)

            # On macOS the supervisor can refuse to report a completed crash
            # if it cannot verify the whole process group's cleanup. That is
            # a mandatory blocked result, not permission to open the PDF.
            original_run = copies.run_limited_converter
            supervision_failures = []

            def observe_supervision(*args, **kwargs):
                try:
                    return original_run(*args, **kwargs)
                except copies.SanitizerProcessExecutionError as error:
                    supervision_failures.append(type(error))
                    raise

            data = valid_pdf()
            with patch.object(copies, "_trusted_converter", return_value=worker), \
                    patch.object(copies, "run_limited_converter",
                                 side_effect=observe_supervision):
                report = copies.attempt_sanitized_pdf_copy(data)
                self.assertIsNotNone(report.failure)
                if supervision_failures:
                    # Only an actual generic supervision error can explain a
                    # launch-failed outcome for this known crashing worker.
                    self.assertEqual(
                        supervision_failures,
                        [copies.SanitizerProcessExecutionError],
                    )
                    expected = copies.SanitizerFailureKind.LAUNCH_FAILED
                else:
                    expected = copies.SanitizerFailureKind.CRASHED
                self.assertEqual(report.failure.kind, expected)
                self.assertIsNone(report.offer)
                self.assertIs(report.permits_open, False)
                self.assertEqual(report.failure.to_dict()["scanVerdict"], "notAssessed")
                self.assertNotIn(str(worker), report.failure.message)
                self.assertIsNone(copies.offer_sanitized_pdf_copy(data))

    def test_timeout_start_error_and_invalid_output_are_not_malware(self):
        data = valid_pdf()
        scenarios = (
            (copies.SanitizerProcessMemoryLimitError("private"),
             copies.SanitizerFailureKind.MEMORY_LIMIT_FAILED),
            (copies.SanitizerProcessTimedOut("private"), copies.SanitizerFailureKind.TIMED_OUT),
            (OSError("/private/secret/file"), copies.SanitizerFailureKind.LAUNCH_FAILED),
        )
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")):
            for error, kind in scenarios:
                with self.subTest(kind=kind), patch.object(
                    copies, "run_limited_converter", side_effect=error
                ):
                    report = copies.attempt_sanitized_pdf_copy(data)
                    self.assertEqual(report.failure.kind, kind)
                    self.assertNotIn("private", report.failure.message)
            for output in (b"", b"not pdf", b"X" * (copies.MAX_OUTPUT_BYTES + 1)):
                with patch.object(
                    copies, "run_limited_converter",
                    return_value=subprocess.CompletedProcess([], 0, output),
                ):
                    self.assertEqual(
                        copies.attempt_sanitized_pdf_copy(data).failure.kind,
                        copies.SanitizerFailureKind.INVALID_OUTPUT,
                    )

    def test_success_is_non_authorizing_and_compatible_with_existing_offer(self):
        data = valid_pdf()
        converted = data + b"changed"
        final = b"%PDF-1.7\nnew sanitized copy"
        with patch.object(copies, "_trusted_converter", return_value=Path("/usr/bin/true")), \
                patch.object(copies, "run_limited_converter",
                             return_value=subprocess.CompletedProcess([], 0, converted)), \
                patch.object(copies, "remove_active_pdf_functionality", return_value=final), \
                patch.object(copies, "_passive_pages", return_value=True), \
                patch.object(copies, "verify_sanitized_pdf_structure") as verify:
            verify.return_value.page_count = 1
            result = copies.attempt_sanitized_pdf_copy(data)
            offer = copies.offer_sanitized_pdf_copy(data)
        self.assertIsNone(result.failure)
        self.assertEqual(result.offer.pdf_bytes, final)
        self.assertIs(result.permits_open, False)
        self.assertEqual(offer.pdf_bytes, final)
        self.assertIs(offer.needs_separate_scan, True)
        self.assertIs(offer.permits_open, False)

    def test_unsupported_or_unavailable_are_distinct_from_crashes(self):
        bad = copies.attempt_sanitized_pdf_copy(b"%PDF invalid")
        self.assertIn(bad.failure.kind, (
            copies.SanitizerFailureKind.UNSUPPORTED_INPUT,
            copies.SanitizerFailureKind.UNAVAILABLE,
        ))
        with patch.object(copies, "_trusted_converter", return_value=None):
            unavailable = copies.attempt_sanitized_pdf_copy(valid_pdf())
        self.assertEqual(unavailable.failure.kind, copies.SanitizerFailureKind.UNAVAILABLE)

    def test_invalid_attempts_cannot_forge_malware_results_or_permissions(self):
        failure = copies._failed(copies.SanitizerFailureKind.CRASHED).failure
        with self.assertRaises(ValueError):
            copies.SanitizerFailureReport(
                copies.SanitizerFailureKind.CRASHED,
                "Malware detected",
            )
        with self.assertRaises(ValueError):
            copies.SanitizerFailureReport(
                copies.SanitizerFailureKind.CRASHED,
                failure.message,
                scan_verdict=ScanResultStatus.malwareDetected.value,
            )
        with self.assertRaises(ValueError):
            copies.SanitizerAttempt(None, None)
        with self.assertRaises(ValueError):
            copies.SanitizerAttempt(None, copies.SanitizerFailureReport(
                copies.SanitizerFailureKind.CRASHED, "untrusted message"))
        with self.assertRaises(FrozenInstanceError):
            failure.permits_open = True

    def test_current_clamav_status_path_and_user_preferences_unchanged(self):
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        scanner = (Path(__file__).resolve().parents[2] / "scan-and-open.py").read_text()
        self.assertNotIn("attempt_sanitized_pdf_copy", scanner)
        self.assertIn("if not cached_clean(cache_id):", scanner)
        self.assertIs(ScanResultStatus.malwareDetected.permits_open, False)


if __name__ == "__main__":
    unittest.main()
