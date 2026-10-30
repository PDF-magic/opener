#!/usr/bin/env python3
"""opener-0280: Standard's mandatory floor matches the deployed Built-in gate.

Standard is still a non-selectable contract. These tests execute the existing
scan-and-open path with synthetic files and controlled ClamAV responses; they
never activate a planned profile, inspect real preferences or open an app.
"""
import importlib.util
import io
from contextlib import redirect_stderr
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from effective_protection_policy import (
    SELECTED_PROFILE_KEY, UnsupportedEffectivePolicy, resolve_effective_policy,
)
from protection_policy_definitions import (
    BASELINE_CONTROLS, ControlAvailability, FailureDisposition, PolicyControl,
    protection_policy_definition,
)
from protection_profiles import ProtectionProfileID

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("parity_scanner", ROOT / "scan-and-open.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class StandardScannerParityTests(unittest.TestCase):
    def stub(self, name, **options):
        patcher = patch.object(gate, name, **options)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="standard-scanner-parity-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / "reference.pdf"
        self.pdf.write_bytes(b"%PDF-1.4\nsynthetic offline regression fixture\n")
        self.stub("CACHE_DB", new=self.root / "clean-cache.sqlite3")
        self.stub("SCAN_REQUEST_DB", new=self.root / "scan-requests.sqlite3")
        self.stub("DATABASE", new=self.root / "signatures")
        self.stub("STAMP", new=self.root / "signatures" / "last-successful-update")
        self.stub("verify_local_file_available")
        self.stub("intended_destination", return_value="com.brave.Browser")
        self.stub("pdf_fallback_application", return_value=None)
        self.stub("record_scan_destination")
        self.verify_target = self.stub("verify_launch_target")
        self.remove_quarantine = self.stub("remove_quarantine")
        self.launch = self.stub("launch_clean_file")
        self.stub("read_signature_database_version", return_value="main=1,daily=2")
        self.stub("scan_engine_version", return_value="ClamAV-test")
        self.stub("record_scan_request")
        self.stub("watch_parent_lifetime")
        self.stub("scanner_path", return_value="/test-clamscan")
        original_policy = gate.ACTIVE_SCAN_POLICY.snapshot()
        self.addCleanup(gate.ACTIVE_SCAN_POLICY.activate, original_policy)
        gate.ACTIVE_SCAN_POLICY.activate(gate.DEFAULT_SCAN_POLICY)

    def test_standard_contract_matches_exactly_the_enforced_baseline(self):
        standard = protection_policy_definition(ProtectionProfileID.STANDARD)
        active = resolve_effective_policy()
        self.assertEqual(
            frozenset(item.control for item in standard.required_checks),
            frozenset(BASELINE_CONTROLS),
        )
        self.assertEqual(active.required_checks, frozenset(BASELINE_CONTROLS))
        self.assertEqual(
            {item.availability for item in standard.required_checks},
            {ControlAvailability.CURRENT},
        )
        self.assertEqual(active.profile_id, "built-in")
        self.assertIs(active.failure_disposition, FailureDisposition.DENY)
        self.assertIs(standard.failure_disposition, FailureDisposition.DENY)
        self.assertFalse(standard.selectable)
        self.assertEqual(
            {(item.control, item.availability) for item in standard.optional_checks},
            {(PolicyControl.PDF_STRUCTURE_VALIDATION, ControlAvailability.PLANNED)},
        )
        with self.assertRaises(UnsupportedEffectivePolicy):
            resolve_effective_policy({SELECTED_PROFILE_KEY: "standard"})

    def test_clean_then_cached_pdf_retains_original_scanner_and_handoff(self):
        clean = subprocess.CompletedProcess([], 0, "reference.pdf: OK\n", "")
        with patch.object(gate, "run_scan_command", return_value=clean) as run:
            first = gate.scan_and_open(str(self.pdf), "/test-clamscan")
            second = gate.scan_and_open(str(self.pdf), "/test-clamscan")
        self.assertEqual(first.status, "clean")
        self.assertFalse(first.from_cache)
        self.assertEqual(first.scanner_version, "ClamAV-test")
        self.assertEqual(second.status, "clean")
        self.assertTrue(second.from_cache)
        self.assertEqual(run.call_count, 1, "unchanged clean PDF must reuse its verified cache")
        command = run.call_args.args[0]
        timeout = run.call_args.kwargs["timeout"]
        self.assertEqual(command[0], "/test-clamscan")
        self.assertEqual(command[-2:], ["--", str(self.pdf)])
        self.assertEqual(timeout, gate.PDF_SCAN_TIMEOUT)
        for flag in (
            "--recursive", "--follow-file-symlinks=2", "--follow-dir-symlinks=2",
            "--alert-exceeds-max=yes", "--alert-encrypted=yes",
            "--max-filesize=0", "--max-scansize=0", "--max-scantime=0", "--no-summary",
            "--database=" + str(gate.DATABASE),
        ):
            self.assertIn(flag, command)
        self.assertEqual(self.remove_quarantine.call_count, 2)
        self.assertEqual(self.verify_target.call_count, 2)
        self.assertEqual(self.launch.call_count, 2)
        for call in self.launch.call_args_list:
            self.assertEqual(call.kwargs["target_app"], "com.brave.Browser")

    def test_pdf_and_other_files_preserve_distinct_existing_scan_limits(self):
        other = self.root / "reference.txt"
        other.write_bytes(self.pdf.read_bytes())
        clean = subprocess.CompletedProcess([], 0, "reference: OK", "")
        with patch.object(gate, "run_scan_command", return_value=clean) as run:
            gate.scan_and_open(str(other), "/test-clamscan")
            gate.scan_and_open(str(self.pdf), "/test-clamscan")
            gate.scan_and_open(str(self.pdf), "/test-clamscan")
        self.assertEqual(run.call_count, 2, "PDF and non-PDF may not share verdicts")
        other_call, pdf_call = run.call_args_list
        self.assertIn("--max-filesize=512M", other_call.args[0])
        self.assertIn("--max-scansize=1024M", other_call.args[0])
        self.assertEqual(other_call.kwargs["timeout"], 180)
        self.assertIn("--max-filesize=0", pdf_call.args[0])
        self.assertIn("--max-scansize=0", pdf_call.args[0])
        self.assertEqual(pdf_call.kwargs["timeout"], gate.PDF_SCAN_TIMEOUT)
        self.assertIsNone(self.launch.call_args_list[0].kwargs["target_app"])

    def test_every_nonclean_scanner_outcome_keeps_quarantine_and_denies_open(self):
        cases = (
            (1, "reference.pdf: Eicar-Test-Signature FOUND", "",
             "Malware was detected"),
            (1, "reference.pdf: Heuristics.Encrypted.PDF FOUND", "",
             "suspicious or unscannable"),
            (2, "", "scanner could not initialize", "could not finish"),
            (0, "reference.pdf: Empty file", "", "did not confirm"),
            (0, "reference.pdf: OK", "WARNING: skipped object", "did not confirm"),
            (0, "", "", "did not confirm"),
        )
        for index, (code, out, err, message) in enumerate(cases):
            with self.subTest(code=code, case=index):
                self.pdf.write_bytes(b"%PDF-1.4\ncase " + str(index).encode())
                self.remove_quarantine.reset_mock()
                self.launch.reset_mock()
                outcome = subprocess.CompletedProcess([], code, out, err)
                with patch.object(gate, "run_scan_command", return_value=outcome) as run:
                    with self.assertRaisesRegex(RuntimeError, message):
                        gate.scan_and_open(str(self.pdf), "/test-clamscan")
                run.assert_called_once()
                self.remove_quarantine.assert_not_called()
                self.launch.assert_not_called()
                digest = gate.policy_cache_key(
                    gate.fingerprint(self.pdf), True, gate.DEFAULT_SCAN_POLICY)
                self.assertIsNone(gate.cached_scan(digest))

    def test_timeout_and_file_mutation_never_open(self):
        with patch.object(gate, "run_scan_command",
                          side_effect=subprocess.TimeoutExpired("/test-clamscan", 10)):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                gate.scan_and_open(str(self.pdf), "/test-clamscan")
        self.remove_quarantine.assert_not_called()
        self.launch.assert_not_called()

        def changed_during_scan(command, timeout):
            self.pdf.write_bytes(b"%PDF-1.4\nreplaced during scanner execution\n")
            return subprocess.CompletedProcess(command, 0, "reference.pdf: OK", "")

        with patch.object(gate, "run_scan_command", side_effect=changed_during_scan):
            with self.assertRaisesRegex(RuntimeError, "file changed"):
                gate.scan_and_open(str(self.pdf), "/test-clamscan")
        self.remove_quarantine.assert_not_called()
        self.launch.assert_not_called()

        def changed_during_quarantine(_path):
            self.pdf.write_bytes(b"%PDF-1.4\nreplaced after scan\n")

        self.remove_quarantine.side_effect = changed_during_quarantine
        with patch.object(gate, "run_scan_command", return_value=
                          subprocess.CompletedProcess([], 0, "reference.pdf: OK", "")):
            with self.assertRaisesRegex(RuntimeError, "file changed"):
                gate.scan_and_open(str(self.pdf), "/test-clamscan")
        self.launch.assert_not_called()

    def test_launch_verification_denial_still_happens_before_quarantine(self):
        self.verify_target.side_effect = RuntimeError("Unsupported PDF destination")
        with patch.object(gate, "run_scan_command", return_value=
                          subprocess.CompletedProcess([], 0, "reference.pdf: OK", "")):
            with self.assertRaisesRegex(RuntimeError, "Unsupported"):
                gate.scan_and_open(str(self.pdf), "/test-clamscan")
        self.remove_quarantine.assert_not_called()
        self.launch.assert_not_called()

    def test_fresh_signature_preflight_is_required_even_with_cached_verdict(self):
        database = gate.DATABASE
        database.mkdir()
        gate.STAMP.write_text(str(time.time()), encoding="ascii")
        (database / "main.cvd").write_bytes(b"synthetic-main")
        # A fresh timestamp without the required daily DB is not sufficient.
        with patch.object(gate, "run_scan_command") as run, redirect_stderr(io.StringIO()):
            self.assertEqual(gate.main([str(self.pdf)]), 1)
            run.assert_not_called()
        (database / "daily.cld").write_bytes(b"synthetic-daily")
        with patch.object(gate, "run_scan_command", return_value=
                          subprocess.CompletedProcess([], 0, "reference.pdf: OK", "")) as run:
            self.assertEqual(gate.main([str(self.pdf)]), 0)
            run.assert_called_once()
        self.remove_quarantine.reset_mock()
        self.launch.reset_mock()
        gate.STAMP.write_text(str(time.time() - 49 * 60 * 60), encoding="ascii")
        with patch.object(gate, "run_scan_command") as run, redirect_stderr(io.StringIO()):
            self.assertEqual(gate.main([str(self.pdf)]), 1)
            run.assert_not_called()
        self.remove_quarantine.assert_not_called()
        self.launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
