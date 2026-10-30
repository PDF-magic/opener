#!/usr/bin/env python3
"""Record only successfully opened original/generated documents, without paths."""

import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    "opened_document_origin_test_scanner", root / "scan-and-open.py"
)
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class OpenedDocumentOriginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()
        self.original = self.directory / "document.pdf"
        self.generated = self.directory / "copy.pdf"
        self.original.write_bytes(b"%PDF-1.4\noriginal")
        self.generated.write_bytes(b"%PDF-1.4\ngenerated")
        self.db = self.directory / "scan-requests.sqlite3"
        for p in (
            patch.object(scanner, "SCAN_REQUEST_DB", self.db),
            patch.object(scanner, "CACHE_DB", self.directory / "scan-cache.sqlite3"),
            patch.object(scanner, "intended_destination", return_value="configured-browser"),
            patch.object(scanner, "pdf_fallback_application", return_value=None),
            patch.object(scanner, "verify_local_file_available"),
            patch.object(scanner, "verify_launch_target"),
            patch.object(scanner, "record_scan_destination"),
            patch.object(scanner, "read_signature_database_version", return_value="main=23"),
            patch.object(scanner, "scan_engine_version", return_value="1.0"),
            patch.object(scanner, "remove_quarantine"),
            patch.object(scanner, "check_database"),
            patch.object(scanner, "scanner_path", return_value="/installed/clamscan"),
        ):
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def clean():
        return subprocess.CompletedProcess([], 0, "example.pdf: OK", "")

    def rows(self):
        if not self.db.exists():
            return []
        with sqlite3.connect(str(self.db)) as connection:
            try:
                return connection.execute(
                    "SELECT document_origin FROM opened_document_origins ORDER BY id"
                ).fetchall()
            except sqlite3.OperationalError:
                return []

    def test_original_and_generated_are_logged_only_after_successful_launch(self):
        order = []
        def launch(path, target_app=None):
            order.append(("launch", path.name))
            self.assertEqual(
                self.rows(),
                [] if path == self.original else [("original",)],
            )
        # Use the actual scanner entrypoints; the optional converter is mocked
        # after its independent validation contract, not its opening decision.
        with patch.object(scanner, "run_scan_command", return_value=self.clean()) as run, \
                patch.object(scanner, "launch_clean_file", side_effect=launch) as opened, \
                patch("maximum_generated_rescan.verified_generated_pdf_bytes",
                      return_value=self.generated.read_bytes()):
            first = scanner.scan_and_open(self.original, "/installed/clamscan")
            self.assertEqual(self.rows(), [("original",)])
            second = scanner.scan_and_open_generated_copy(self.generated, object())
        self.assertEqual(first.status, "clean")
        self.assertEqual(second.status, "clean")
        self.assertFalse(second.from_cache)
        self.assertEqual(self.rows(), [("original",), ("generated-copy",)])
        self.assertEqual(opened.call_count, 2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual([event[0] for event in order], ["launch", "launch"])

    def test_cached_original_still_records_original_after_launch(self):
        with patch.object(scanner, "run_scan_command", return_value=self.clean()), \
                patch.object(scanner, "launch_clean_file"):
            scanner.scan_and_open(self.original, "/installed/clamscan")
        with patch.object(scanner, "run_scan_command") as run, \
                patch.object(scanner, "launch_clean_file"):
            cached = scanner.scan_and_open(self.original, "/installed/clamscan")
        run.assert_not_called()
        self.assertTrue(cached.from_cache)
        self.assertEqual(self.rows(), [("original",), ("original",)])

    def test_untrusted_protection_level_cannot_mark_document_as_generated(self):
        with patch.object(scanner, "run_scan_command", return_value=self.clean()), \
                patch.object(scanner, "launch_clean_file"):
            scanner.scan_and_open(
                self.original, "/installed/clamscan",
                protection_level="generated-copy",
            )
        self.assertEqual(self.rows(), [("original",)])

    def test_infected_or_incomplete_scan_does_not_record_opening(self):
        cases = (
            subprocess.CompletedProcess([], 1, "example.pdf: Malware FOUND", ""),
            subprocess.CompletedProcess([], 2, "", "failed to scan"),
            subprocess.CompletedProcess([], 0, "example.pdf: skipped", ""),
            subprocess.TimeoutExpired(["secret path"], 2),
        )
        for outcome in cases:
            with self.subTest(type=type(outcome).__name__), \
                    patch.object(scanner, "run_scan_command",
                                 **({"return_value": outcome}
                                    if isinstance(outcome, subprocess.CompletedProcess)
                                    else {"side_effect": outcome})), \
                    patch.object(scanner, "launch_clean_file") as launch:
                with self.assertRaises(RuntimeError):
                    scanner.scan_and_open(self.original, "/installed/clamscan")
                launch.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_failed_primary_and_fallback_launch_not_recorded(self):
        with patch.object(scanner, "run_scan_command", return_value=self.clean()), \
                patch.object(scanner, "pdf_fallback_application", return_value="fallback"), \
                patch.object(scanner, "launch_clean_file", side_effect=OSError("failed")):
            with self.assertRaises(scanner.LaunchFailedError):
                scanner.scan_and_open(self.original, "/installed/clamscan")
        self.assertEqual(self.rows(), [])

    def test_successful_fallback_records_one_original(self):
        targets = []
        def launch(path, target_app=None):
            targets.append(target_app)
            if len(targets) == 1:
                raise OSError("primary unavailable")
        with patch.object(scanner, "run_scan_command", return_value=self.clean()), \
                patch.object(scanner, "pdf_fallback_application", return_value="fallback"), \
                patch.object(scanner, "launch_clean_file", side_effect=launch):
            scanner.scan_and_open(self.original, "/installed/clamscan")
        self.assertEqual(targets, ["configured-browser", "fallback"])
        self.assertEqual(self.rows(), [("original",)])

    def test_mismatched_generated_bytes_never_record_opening(self):
        with patch("maximum_generated_rescan.verified_generated_pdf_bytes",
                   return_value=b"%PDF-1.4\nnot the copy"), \
                patch.object(scanner, "run_scan_command") as run, \
                patch.object(scanner, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "differs from"):
                scanner.scan_and_open_generated_copy(self.generated, object())
        run.assert_not_called()
        launch.assert_not_called()
        self.assertEqual(self.rows(), [])

    def test_records_are_private_and_never_include_paths_or_pdf_text(self):
        with patch.object(scanner, "run_scan_command", return_value=self.clean()), \
                patch.object(scanner, "launch_clean_file"):
            scanner.scan_and_open(self.original, "/installed/clamscan")
        self.assertEqual(self.rows(), [("original",)])
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)
        stored = self.db.read_bytes()
        self.assertNotIn(str(self.directory).encode(), stored)
        self.assertNotIn(self.original.name.encode(), stored)
        self.assertNotIn(b"%PDF-", stored)
        self.assertNotIn(b"configured-browser", stored)

    def test_audit_failures_never_override_successful_scanner_or_launch(self):
        unsafe = self.directory / "unsafe-db"
        target = self.directory / "sentinel"
        target.write_text("unchanged")
        unsafe.symlink_to(target)
        with patch.object(scanner, "SCAN_REQUEST_DB", unsafe), \
                patch.object(scanner, "run_scan_command", return_value=self.clean()), \
                patch.object(scanner, "launch_clean_file") as launch:
            outcome = scanner.scan_and_open(self.original, "/installed/clamscan")
        self.assertEqual(outcome.status, "clean")
        launch.assert_called_once()
        self.assertEqual(target.read_text(), "unchanged")
        self.assertFalse(scanner.record_opened_document_origin("not-valid"))
        self.assertEqual(self.rows(), [])

    def test_scanner_and_user_preferences_are_unchanged(self):
        from protection_profiles import PROTECTION_PROFILES, ProtectionProfileID
        self.assertFalse(PROTECTION_PROFILES[ProtectionProfileID.MAXIMUM].selectable)
        scanner_source = (root / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("if not cached_clean(cache_id):", scanner_source)
        self.assertIn("if requires_scan():", scanner_source)
        self.assertNotIn("from maximum_sanitized_copy", scanner_source)


if __name__ == "__main__":
    unittest.main()
