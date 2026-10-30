#!/usr/bin/env python3
"""opener-0405: regression tests for installed scanner configuration boundaries.

These tests exercise existing Built-in limits; they do not introduce optional
settings or permit weaker malware, quarantine, cache, or launch behavior.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from scanner_argument_validation import (
    InvalidScannerArguments,
    validate_scanner_arguments,
)

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "scanner_configuration_boundary_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ScannerConfigurationBoundaryTests(unittest.TestCase):
    def test_pdf_timeout_accepts_inclusive_boundaries_only(self):
        for seconds in (1, 2, gate.PDF_SCAN_TIMEOUT - 1, gate.PDF_SCAN_TIMEOUT):
            with self.subTest(seconds=seconds):
                policy = gate.ScanSecurityPolicySnapshot(pdf_timeout_seconds=seconds)
                self.assertEqual(policy.pdf_timeout_seconds, seconds)

        for invalid in (0, -1, gate.PDF_SCAN_TIMEOUT + 1,
                        True, False, 1.0, float("nan"), float("inf"),
                        "1", None):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                gate.ScanSecurityPolicySnapshot(pdf_timeout_seconds=invalid)

    def test_other_timeout_accepts_inclusive_boundaries_only(self):
        for seconds in (1, 2, 179, 180):
            with self.subTest(seconds=seconds):
                policy = gate.ScanSecurityPolicySnapshot(other_timeout_seconds=seconds)
                self.assertEqual(policy.other_timeout_seconds, seconds)

        for invalid in (0, -1, 181, True, False, 1.0, float("nan"),
                        float("inf"), "180", None):
            with self.subTest(invalid=repr(invalid)), self.assertRaises(ValueError):
                gate.ScanSecurityPolicySnapshot(other_timeout_seconds=invalid)

    def test_valid_boundary_snapshots_are_independent_and_not_published(self):
        current = gate.ACTIVE_SCAN_POLICY.snapshot()
        minimum = gate.ScanSecurityPolicySnapshot(
            pdf_timeout_seconds=1, other_timeout_seconds=1
        )
        maximum = gate.ScanSecurityPolicySnapshot(
            pdf_timeout_seconds=gate.PDF_SCAN_TIMEOUT, other_timeout_seconds=180
        )
        self.assertEqual(maximum, gate.DEFAULT_SCAN_POLICY)
        self.assertIs(gate.ACTIVE_SCAN_POLICY.snapshot(), current)
        self.assertNotEqual(
            gate.policy_cache_key(b"fixed-test-digest", True, minimum),
            gate.policy_cache_key(b"fixed-test-digest", True, maximum),
        )
        self.assertNotEqual(
            gate.policy_cache_key(b"fixed-test-digest", False, minimum),
            gate.policy_cache_key(b"fixed-test-digest", False, maximum),
        )
        self.assertEqual(gate.MAX_CONCURRENT_SCANS, 2)

    def test_argv_boundary_validation_keeps_mandatory_scanner_flags(self):
        scanner = "/opt/homebrew/bin/clamscan"
        database = Path("/temporary/signatures")
        document = Path("/temporary/document.pdf")
        for is_pdf, maximum in ((True, gate.PDF_SCAN_TIMEOUT), (False, 180)):
            size_flags = (
                ("--max-filesize=0", "--max-scansize=0") if is_pdf else
                ("--max-filesize=512M", "--max-scansize=1024M")
            )
            command = [
                scanner, "--database=" + str(database), "--recursive",
                "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
                "--alert-exceeds-max=yes", "--alert-encrypted=yes",
                *size_flags, "--max-scantime=0", "--no-summary", "--",
                str(document),
            ]
            def validate(timeout):
                return validate_scanner_arguments(
                    command, scanner=scanner, database=database,
                    document=document, is_pdf=is_pdf, timeout=timeout
                )
            for seconds in (1, maximum - 1, maximum):
                with self.subTest(is_pdf=is_pdf, seconds=seconds):
                    validate(seconds)
            for invalid in (0, -1, maximum + 1, True, 1.0, "1", None):
                with self.subTest(is_pdf=is_pdf, invalid=repr(invalid)):
                    with self.assertRaises(InvalidScannerArguments):
                        validate(invalid)
            self.assertIn("--alert-encrypted=yes", command)
            self.assertIn("--alert-exceeds-max=yes", command)
            self.assertEqual(command[-2], "--")

    def test_nonpdf_file_size_boundary_is_inclusive_without_relaxing_pdf_gate(self):
        with tempfile.TemporaryDirectory(prefix="scanner-config-boundaries-") as tmp:
            root = Path(tmp)
            ordinary = root / "document.txt"
            pdf = root / "document.pdf"
            bundle = root / "Example.app"
            bundle.mkdir()
            member = bundle / "member.txt"
            # Use a small mocked ceiling so the same real boundary logic is
            # exercised without creating or hashing a 512 MiB test document.
            with patch.object(gate, "MAX_FILE_SIZE", 4):
                ordinary.write_bytes(b"1234")
                self.assertIsInstance(gate.fingerprint(ordinary), bytes)
                ordinary.write_bytes(b"12345")
                with self.assertRaisesRegex(RuntimeError, "512 MB scan limit"):
                    gate.fingerprint(ordinary)
                pdf.write_bytes(b"12345")
                self.assertIsInstance(gate.fingerprint(pdf), bytes)
                ordinary.write_bytes(b"")
                with self.assertRaisesRegex(RuntimeError, "zero-length"):
                    gate.fingerprint(ordinary)
                member.write_bytes(b"12345")
                with self.assertRaisesRegex(RuntimeError, "512 MB scan limit"):
                    gate.fingerprint(bundle)


if __name__ == "__main__":
    unittest.main()
