#!/usr/bin/env python3
"""Exercise opt-in, fail-closed PDF fallback selection through the real scan gate."""
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import file_launcher as launcher

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fallback_scan_gate", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class FallbackTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.pdf = self.root / "quarterly – report.PDF"
        self.pdf.write_bytes(b"%PDF-1.4\nsafe test document")
        self.preference = self.root / "target-app.txt"
        self.preference.write_text("com.brave.Browser\n")
        self.fallback = self.root / "fallback-app.txt"
        self.fallback.write_text("com.apple.Preview\n")
        for obj, setting, value in (
            (launcher, "TARGET_APP_CONFIG", self.preference),
            (launcher, "FALLBACK_APP_CONFIG", self.fallback),
            (opener, "CACHE_DB", self.root / "cache.sqlite3"),
            (opener, "SCAN_REQUEST_DB", self.root / "requests.sqlite3"),
        ):
            control = patch.object(obj, setting, value)
            control.start()
            self.addCleanup(control.stop)

    def destinations(self):
        with sqlite3.connect(opener.SCAN_REQUEST_DB) as db:
            return [entry[0] for entry in db.execute(
                "SELECT intended_destination_application FROM scan_requests ORDER BY rowid")]

    def runner(self, *, reject=(), fail_launch=()):
        commands = []
        def execute(command, *args, **kwargs):
            commands.append(command)
            if command[0] == str(launcher.PDF_TARGET_VERIFIER) and command[1] in reject:
                return subprocess.CompletedProcess(command, 1, "", "not registered")
            if command[0] == str(launcher.NATIVE_LAUNCHER) and "--bundle-id" in command and command[2] in fail_launch:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, "file: OK", "")
        return commands, execute

    def test_missing_fallback_leaves_primary_only(self):
        self.fallback.unlink()
        self.assertIsNone(launcher.pdf_fallback_application("com.brave.Browser"))
        commands, execute = self.runner()
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine") as quarantine:
            outcome = opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(outcome.status, "clean")
        self.assertEqual([c[1] for c in commands if c[0] == str(launcher.PDF_TARGET_VERIFIER)],
                         ["com.brave.Browser"])
        self.assertEqual(self.destinations(), ["com.brave.Browser"])
        quarantine.assert_called_once()

    def test_preflight_failure_uses_verified_fallback_before_quarantine(self):
        commands, execute = self.runner(reject={"com.brave.Browser"})
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine") as quarantine:
            outcome = opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(outcome.status, "clean")
        self.assertEqual([c[1] for c in commands if c[0] == str(launcher.PDF_TARGET_VERIFIER)],
                         ["com.brave.Browser", "com.apple.Preview"])
        launches = [c for c in commands if c[0] == str(launcher.NATIVE_LAUNCHER)]
        self.assertEqual(launches, [[str(launcher.NATIVE_LAUNCHER),
                                     "--bundle-id", "com.apple.Preview", str(self.pdf)]])
        self.assertEqual(self.destinations(), ["com.brave.Browser", "com.apple.Preview"])
        quarantine.assert_called_once()

    def test_primary_launch_failure_uses_prevalidated_fallback(self):
        commands, execute = self.runner(fail_launch={"com.brave.Browser"})
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine") as quarantine, \
             patch.object(opener, "verify_file_integrity", wraps=opener.verify_file_integrity) as check:
            outcome = opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(outcome.status, "clean")
        self.assertEqual([c[1] for c in commands if c[0] == str(launcher.PDF_TARGET_VERIFIER)],
                         ["com.brave.Browser", "com.apple.Preview"])
        launches = [c[2] for c in commands if c[0] == str(launcher.NATIVE_LAUNCHER)]
        self.assertEqual(launches, ["com.brave.Browser", "com.apple.Preview"])
        self.assertEqual(self.destinations(), ["com.brave.Browser", "com.apple.Preview"])
        # Quarantine stays intact through primary and fallback handoffs.
        self.assertGreaterEqual(check.call_count, 2)
        self.assertFalse(any(call.kwargs.get("allow_ctime_change") is True
                             for call in check.call_args_list))
        quarantine.assert_called_once()

    def test_unverified_fallback_does_not_displace_working_primary(self):
        commands, execute = self.runner(reject={"com.apple.Preview"})
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine"):
            opener.scan_and_open(str(self.pdf), "/scanner")
        launches = [c[2] for c in commands if c[0] == str(launcher.NATIVE_LAUNCHER)]
        self.assertEqual(launches, ["com.brave.Browser"])
        self.assertEqual(self.destinations(), ["com.brave.Browser"])

    def test_unverified_fallback_never_receives_launch_after_primary_failure(self):
        commands, execute = self.runner(reject={"com.apple.Preview"}, fail_launch={"com.brave.Browser"})
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine"):
            with self.assertRaises(opener.LaunchFailedError):
                opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual([c[2] for c in commands if c[0] == str(launcher.NATIVE_LAUNCHER)],
                         ["com.brave.Browser"])
        self.assertEqual(self.destinations(), ["com.brave.Browser"])

    def test_both_launches_failing_keep_clean_scan_result(self):
        commands, execute = self.runner(fail_launch={"com.brave.Browser", "com.apple.Preview"})
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine"):
            with self.assertRaises(opener.LaunchFailedError) as err:
                opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(err.exception.scan_result.status, "clean")
        self.assertEqual([c[2] for c in commands if c[0] == str(launcher.NATIVE_LAUNCHER)],
                         ["com.brave.Browser", "com.apple.Preview"])

    def test_blocked_scan_does_not_preflight_or_launch_fallback(self):
        commands = []
        def execute(command, *args, **kwargs):
            commands.append(command)
            if command[0] == "/scanner":
                return subprocess.CompletedProcess(command, 1, "PDF: Malware FOUND", "")
            return subprocess.CompletedProcess(command, 0, "", "")
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine") as quarantine:
            with self.assertRaisesRegex(RuntimeError, "Malware"):
                opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertFalse(any(c[0] in (str(launcher.NATIVE_LAUNCHER),
                                     str(launcher.PDF_TARGET_VERIFIER)) for c in commands))
        quarantine.assert_not_called()

    def test_invalid_or_symlinked_fallback_blocks_before_scan(self):
        for value in ("", "Preview", "--evil", "com..bad",
                      "local.studio.brave-pdf-opener", "system-default-browser",
                      "com.apple.Preview\ncom.google.Chrome", "x" * 260):
            with self.subTest(value=value[:20]):
                self.fallback.write_text(value)
                with patch.object(opener.subprocess, "run") as run, \
                     patch.object(opener, "remove_quarantine") as quarantine:
                    with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                        opener.scan_and_open(str(self.pdf), "/scanner")
                run.assert_not_called()
                quarantine.assert_not_called()
        self.fallback.unlink()
        target = self.root / "outside"
        target.write_text("com.apple.Preview\n")
        self.fallback.symlink_to(target)
        with self.assertRaises(RuntimeError):
            launcher.pdf_fallback_application()

    def test_same_fallback_as_primary_does_not_repeat_launch(self):
        self.fallback.write_text("com.brave.Browser\n")
        self.assertIsNone(launcher.pdf_fallback_application("com.brave.Browser"))
        commands, execute = self.runner(fail_launch={"com.brave.Browser"})
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine"):
            with self.assertRaises(opener.LaunchFailedError):
                opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual([c[2] for c in commands if c[0] == str(launcher.NATIVE_LAUNCHER)],
                         ["com.brave.Browser"])

    def test_non_pdf_ignores_pdf_fallback(self):
        self.fallback.write_text("not a valid ID")
        txt = self.root / "notes.txt"
        txt.write_text("text")
        commands, execute = self.runner()
        with patch.object(opener.subprocess, "run", side_effect=execute), \
             patch.object(opener, "remove_quarantine"):
            opener.scan_and_open(str(txt), "/scanner")
        self.assertEqual([c for c in commands if c[0] == str(launcher.NATIVE_LAUNCHER)],
                         [[str(launcher.NATIVE_LAUNCHER), str(txt)]])

if __name__ == "__main__":
    unittest.main()
