#!/usr/bin/env python3
"""opener-1098: cross-boundary security regressions for the active scan gate.

All PDFs and cache files are synthetic and disposable. Scanner and native
handoff calls are mocked; no installed signatures or user preferences are read.
"""

from contextlib import ExitStack
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scanner_argument_validation import InvalidScannerArguments


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "security_regression_scan_gate", ROOT / "scan-and-open.py"
)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ScanGateSecurityRegressions(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-1098-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / '--unsafe; $(touch injected).PDF'
        self.original = b"%PDF-1.4\nSynthetic inert regression input\n%%EOF\n"
        self.pdf.write_bytes(self.original)

    def mock_boundaries(self, stack, scanner_results, *, cache_name="cache.sqlite3"):
        """Keep the real gate, identity verification, and cache policy active."""
        for name, value in (
            ("CACHE_DB", self.root / cache_name),
            ("SCAN_REQUEST_DB", self.root / "requests.sqlite3"),
            ("DATABASE", self.root / "synthetic-signatures"),
        ):
            stack.enter_context(patch.object(gate, name, value))
        stack.enter_context(patch.object(
            gate, "intended_destination", return_value="com.brave.Browser"
        ))
        # A configured fallback must not rescue an unclean scanner verdict.
        stack.enter_context(patch.object(
            gate, "pdf_fallback_application", return_value="com.apple.Preview"
        ))
        stack.enter_context(patch.object(gate, "verify_local_file_available"))
        stack.enter_context(patch.object(gate, "verify_launch_target"))
        stack.enter_context(patch.object(gate, "record_scan_destination"))
        stack.enter_context(patch.object(gate, "record_opened_document_origin"))
        stack.enter_context(patch.object(
            gate, "scan_engine_version", return_value=None
        ))
        stack.enter_context(patch.object(
            gate, "read_signature_database_version", return_value=None
        ))
        run = stack.enter_context(patch.object(
            gate, "run_scan_command", side_effect=scanner_results
        ))
        quarantine = stack.enter_context(
            patch.object(gate, "remove_quarantine")
        )
        launch = stack.enter_context(patch.object(gate, "launch_clean_file"))
        return run, quarantine, launch

    def scan(self, *, scanner="/synthetic/clamscan"):
        return gate.scan_and_open(
            str(self.pdf), scanner,
            source_url="https://example.invalid/claimed-clean.pdf",
            protection_level="user-selected-preview",
        )

    def test_adversarial_scanner_verdicts_never_enable_handoff_or_cache(self):
        cases = (
            (1, "report: Trojan.Test FOUND", ""),
            (2, "report: OK", "scanner initialization failed"),
            (0, "report: OK\nreport: Trojan.Test FOUND", ""),
            (0, "warning: skipped\nreport: OK", ""),
            (0, "report: OK", "WARNING: unreadable bytes"),
            (0, "report: Empty file", ""),
            (0, "", ""),
            (0, "report: OK\nreport: skipped", ""),
        )
        for index, (exit_code, stdout, stderr) in enumerate(cases):
            with self.subTest(exit_code=exit_code, stdout=stdout, stderr=stderr):
                outcome = subprocess.CompletedProcess(
                    ["/synthetic/clamscan"], exit_code, stdout, stderr
                )
                with ExitStack() as stack:
                    run, quarantine, launch = self.mock_boundaries(
                        stack, [outcome], cache_name=f"failed-{index}.sqlite3"
                    )
                    with patch.object(gate, "remember_clean") as remember:
                        with self.assertRaises(RuntimeError) as failure:
                            self.scan()
                    run.assert_called_once()
                    command = run.call_args.args[0]
                    self.assertEqual(command[-2:], ["--", str(self.pdf)])
                    self.assertIn("--alert-encrypted=yes", command)
                    self.assertIn("--alert-exceeds-max=yes", command)
                    self.assertNotIn("--alert-encrypted=no", command)
                    self.assertNotIn("--exclude", command)
                    self.assertNotIn(str(self.pdf), str(failure.exception))
                    self.assertNotIn("user-selected-preview", str(failure.exception))
                    remember.assert_not_called()
                    quarantine.assert_not_called()
                    launch.assert_not_called()
                self.assertEqual(self.pdf.read_bytes(), self.original)
                self.assertFalse((self.root / "injected").exists())

    def test_failed_scan_requires_new_verdict_before_opening_and_cache_reuse(self):
        failed = subprocess.CompletedProcess([], 2, "report: OK", "scanner failure")
        clean = subprocess.CompletedProcess([], 0, "report: OK", "")
        with ExitStack() as stack:
            run, quarantine, launch = self.mock_boundaries(stack, [failed, clean])
            with self.assertRaises(RuntimeError):
                self.scan()
            self.assertEqual(run.call_count, 1)
            launch.assert_not_called()
            quarantine.assert_not_called()

            accepted = self.scan()
            self.assertEqual(accepted.status, "clean")
            self.assertFalse(accepted.from_cache)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(launch.call_count, 1)

            reused = self.scan()
            self.assertEqual(reused.status, "clean")
            self.assertTrue(reused.from_cache)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(launch.call_count, 2)
        self.assertEqual(self.pdf.read_bytes(), self.original)

    def test_cached_clean_bytes_cannot_authorize_modified_pdf(self):
        clean = subprocess.CompletedProcess([], 0, "report: OK", "")
        infected = subprocess.CompletedProcess([], 1, "report: Trojan.Test FOUND", "")
        with ExitStack() as stack:
            run, quarantine, launch = self.mock_boundaries(
                stack, [clean, infected]
            )
            self.assertEqual(self.scan().status, "clean")
            self.pdf.write_bytes(self.original + b"new bytes after clean scan")
            with self.assertRaises(RuntimeError):
                self.scan()
            self.assertEqual(run.call_count, 2)
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(quarantine.call_count, 1)
        self.assertTrue(self.pdf.read_bytes().endswith(b"new bytes after clean scan"))

    def test_postscan_replacement_blocks_even_an_explicit_clean_verdict(self):
        modified = self.original + b"replaced before handoff"

        def replace_then_report_ok(command, timeout):
            self.pdf.write_bytes(modified)
            return subprocess.CompletedProcess(command, 0, "report: OK", "")

        with ExitStack() as stack:
            run, quarantine, launch = self.mock_boundaries(
                stack, replace_then_report_ok
            )
            with patch.object(gate, "remember_clean") as remember:
                with self.assertRaisesRegex(RuntimeError, "changed"):
                    self.scan()
            run.assert_called_once()
            remember.assert_not_called()
            quarantine.assert_not_called()
            launch.assert_not_called()
        self.assertEqual(self.pdf.read_bytes(), modified)

    def test_cached_success_cannot_skip_scanner_executable_validation(self):
        clean = subprocess.CompletedProcess([], 0, "report: OK", "")
        with ExitStack() as stack:
            run, quarantine, launch = self.mock_boundaries(stack, [clean])
            self.assertEqual(self.scan().status, "clean")
            with self.assertRaises(InvalidScannerArguments):
                self.scan(scanner="clamscan")
            run.assert_called_once()
            launch.assert_called_once()
            quarantine.assert_called_once()
        self.assertEqual(self.pdf.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
