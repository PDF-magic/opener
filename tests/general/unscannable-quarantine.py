#!/usr/bin/env python3
"""opener-0817: quarantine survives inputs that ClamAV cannot verify.

Linux exercises the actual fail-closed scan gate with isolated test files;
macOS repeats those paths with a real com.apple.quarantine extended attribute.
No real scanner, native application, user document or preference is touched.
"""

from contextlib import ExitStack
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("unscannable_quarantine_gate",
                                              ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)

ATTRIBUTE = "com.apple.quarantine"
MARKER = b"0081;00000000;PDFMagicOpener;00000000-0000-0000-0000-000000000000"
PDF = b"%PDF-1.4\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n"


class UnscannableQuarantineTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix="opener-unscannable-")
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.pdf = self.root / "unscannable.pdf"
        self.pdf.write_bytes(PDF)

    def tag_quarantine(self, path):
        if sys.platform == "darwin":
            os.setxattr(path, ATTRIBUTE, MARKER)
            return os.getxattr(path, ATTRIBUTE)
        return None

    def assert_quarantine_intact(self, path, expected):
        if expected is not None:
            self.assertEqual(os.getxattr(path, ATTRIBUTE), expected)
        self.assertEqual(path.read_bytes(), PDF if path == self.pdf else b"")

    def assert_unscannable_is_blocked(self, outcome, *, expected_message):
        original = self.tag_quarantine(self.pdf)
        with ExitStack() as stack:
            stack.enter_context(patch.object(gate, "CACHE_DB",
                                             self.root / "cache.sqlite"))
            stack.enter_context(patch.object(gate, "SCAN_REQUEST_DB",
                                             self.root / "requests.sqlite"))
            stack.enter_context(patch.object(gate, "intended_destination",
                                             return_value="com.brave.Browser"))
            stack.enter_context(patch.object(gate, "pdf_fallback_application",
                                             return_value=None))
            stack.enter_context(patch.object(gate, "record_scan_destination"))
            stack.enter_context(patch.object(gate, "read_signature_database_version",
                                             return_value=None))
            stack.enter_context(patch.object(gate, "verify_local_file_available"))
            scanner = stack.enter_context(patch.object(
                gate, "run_scan_command", side_effect=outcome
                if isinstance(outcome, BaseException) else None,
                return_value=None if isinstance(outcome, BaseException) else outcome))
            cache = stack.enter_context(patch.object(gate, "remember_clean"))
            hook = stack.enter_context(patch.object(gate, "remove_quarantine"))
            launched = stack.enter_context(patch.object(gate, "launch_clean_file"))
            fallback = stack.enter_context(patch.object(gate, "verify_launch_target"))
            opened = stack.enter_context(patch.object(gate, "record_opened_document_origin"))
            with self.assertRaisesRegex(RuntimeError, expected_message) as failure:
                gate.scan_and_open(str(self.pdf), "/scanner")
            self.assertNotIn(str(self.pdf), str(failure.exception))
            scanner.assert_called_once()
            cache.assert_not_called()
            hook.assert_not_called()
            launched.assert_not_called()
            fallback.assert_not_called()
            opened.assert_not_called()
        self.assert_quarantine_intact(self.pdf, original)

    def test_scanner_unscannable_results_never_release_quarantine(self):
        cases = (
            ("heuristic-scan-limits", subprocess.CompletedProcess(
                [], 1, "unscannable.pdf: Heuristics.Limits.Exceeded FOUND", ""),
             "suspicious or unscannable"),
            ("scanner-error", subprocess.CompletedProcess(
                [], 2, "", "ERROR: unreadable input"), "could not finish"),
            ("partial-output", subprocess.CompletedProcess(
                [], 0, "unscannable.pdf: OK\nWARNING: skipped embedded item", ""),
             "did not confirm a complete scan"),
            ("ambiguous-success", subprocess.CompletedProcess(
                [], 0, "unscannable.pdf: Empty file", ""),
             "did not confirm a complete scan"),
            ("stderr-warning", subprocess.CompletedProcess(
                [], 0, "unscannable.pdf: OK", "LibClamAV Warning: read failed"),
             "did not confirm a complete scan"),
            ("scanner-timeout", subprocess.TimeoutExpired(
                ["/scanner", "/private/hidden.pdf"], 1), "scan timed out"),
        )
        for name, result, message in cases:
            with self.subTest(case=name):
                # A fresh test fixture and DB per case avoid cached-clean contamination.
                self.pdf.write_bytes(PDF)
                self.assert_unscannable_is_blocked(result, expected_message=message)

    def test_empty_unscannable_file_keeps_quarantine_before_scanner(self):
        empty = self.root / "empty.pdf"
        empty.write_bytes(b"")
        original = self.tag_quarantine(empty)
        with patch.object(gate, "CACHE_DB", self.root / "empty-cache.sqlite"), \
             patch.object(gate, "run_scan_command") as scanner, \
             patch.object(gate, "remember_clean") as cache, \
             patch.object(gate, "remove_quarantine") as hook, \
             patch.object(gate, "launch_clean_file") as launch:
            with self.assertRaisesRegex(RuntimeError, "zero-length file cannot be scanned"):
                gate.scan_and_open(str(empty), "/scanner")
        scanner.assert_not_called()
        cache.assert_not_called()
        hook.assert_not_called()
        launch.assert_not_called()
        self.assert_quarantine_intact(empty, original)

    @unittest.skipUnless(sys.platform == "darwin" and hasattr(os, "setxattr"),
                         "Requires the real macOS quarantine extended attribute")
    def test_real_macos_quarantine_survives_failed_scan_and_timeout(self):
        for failure, message in (
            (subprocess.CompletedProcess([], 2, "", "ERROR: cannot read"), "could not finish"),
            (subprocess.TimeoutExpired(["/scanner"], 1), "scan timed out"),
        ):
            with self.subTest(message=message):
                self.assert_unscannable_is_blocked(failure, expected_message=message)

    def test_no_quarantine_removal_or_preference_modification_is_added(self):
        scanner = (ROOT / "scan-and-open.py").read_text(encoding="utf-8")
        self.assertIn("def remove_quarantine(path):", scanner)
        self.assertIn("    return None", scanner.split(
            "def remove_quarantine(path):", 1)[1].split(
                "@dataclass(frozen=True)", 1)[0])
        self.assertIn("if not decision.allowed:", scanner)
        self.assertIn("remove_quarantine(path)", scanner)
        self.assertNotIn("UserDefaults", scanner)


if __name__ == "__main__":
    unittest.main()
