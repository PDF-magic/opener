#!/usr/bin/env python3
"""Verify Microsoft Edge PDF routing without weakening the malware scan gate."""

import importlib.util
import sqlite3
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import file_launcher as launcher


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("scan_and_open_edge", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)
EDGE_BUNDLE_ID = "com.microsoft.edgemac"


class MicrosoftEdgeLaunchingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.document = self.root / "Edge example π.PDF"
        self.document.write_bytes(b"%PDF-1.4\nTest document")
        self.config = self.root / "target-app.txt"
        self.config.write_text(EDGE_BUNDLE_ID + "\n")
        for obj, key, value in (
            (launcher, "TARGET_APP_CONFIG", self.config),
            (opener, "CACHE_DB", self.root / "clean-cache.sqlite3"),
            (opener, "SCAN_REQUEST_DB", self.root / "request-log.sqlite3"),
        ):
            setting = patch.object(obj, key, value)
            setting.start()
            self.addCleanup(setting.stop)

    def test_edge_runs_only_after_clean_scan_and_pdf_verification(self):
        def execute(command, *args, **kwargs):
            return subprocess.CompletedProcess(command, 0, "file: OK", "")

        with patch.object(opener.subprocess, "run", side_effect=execute) as run, \
                patch.object(opener, "remove_quarantine") as quarantine:
            opener.scan_and_open(str(self.document), "/scanner")

        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(launcher.pdf_target_application(), EDGE_BUNDLE_ID)
        self.assertEqual(commands[0][0], "/scanner")
        self.assertIn("--alert-encrypted=yes", commands[0])
        self.assertIn([str(launcher.PDF_TARGET_VERIFIER), EDGE_BUNDLE_ID], commands)
        self.assertEqual(commands[-1], [
            str(launcher.NATIVE_LAUNCHER), "--bundle-id", EDGE_BUNDLE_ID,
            str(self.document),
        ])
        self.assertLess(commands.index([str(launcher.PDF_TARGET_VERIFIER), EDGE_BUNDLE_ID]),
                        len(commands) - 1)
        quarantine.assert_called_once()
        with sqlite3.connect(opener.SCAN_REQUEST_DB) as database:
            recorded = database.execute(
                "SELECT intended_destination_application FROM scan_requests"
            ).fetchone()
        self.assertEqual(recorded, (EDGE_BUNDLE_ID,))

    def test_unavailable_or_unregistered_edge_never_opens_or_clears_quarantine(self):
        errors = (
            subprocess.CompletedProcess([], 1, "", "not registered"),
            FileNotFoundError("verification helper unavailable"),
            subprocess.TimeoutExpired("verification helper", 10),
        )
        for outcome in errors:
            with self.subTest(outcome=type(outcome).__name__):
                def execute(command, *args, **kwargs):
                    if command[0] == str(launcher.PDF_TARGET_VERIFIER):
                        if isinstance(outcome, Exception):
                            raise outcome
                        return outcome
                    if command[0] == str(launcher.NATIVE_LAUNCHER):
                        self.fail("An unverified Edge destination must not launch")
                    return subprocess.CompletedProcess(command, 0, "file: OK", "")

                with patch.object(opener.subprocess, "run", side_effect=execute) as run, \
                        patch.object(opener, "remove_quarantine") as quarantine:
                    with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                        opener.scan_and_open(str(self.document), "/scanner")
                self.assertTrue(any(
                    call.args[0][0] == str(launcher.PDF_TARGET_VERIFIER)
                    for call in run.call_args_list
                ))
                quarantine.assert_not_called()

    def test_detected_malware_never_reaches_edge_preflight_or_launch(self):
        detected = subprocess.CompletedProcess([], 1, "file: Malware FOUND", "")
        with patch.object(opener.subprocess, "run", return_value=detected) as run, \
                patch.object(opener, "remove_quarantine") as quarantine:
            with self.assertRaisesRegex(RuntimeError, "Malware"):
                opener.scan_and_open(str(self.document), "/scanner")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], "/scanner")
        quarantine.assert_not_called()

    def test_non_pdf_keeps_the_default_handler_even_when_edge_is_configured(self):
        other = self.root / "ordinary.txt"
        other.write_text("safe")
        with patch.object(opener.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, "file: OK", "")) as run, \
                patch.object(opener, "remove_quarantine") as quarantine:
            opener.scan_and_open(str(other), "/scanner")
        self.assertEqual(run.call_args.args[0], [str(launcher.NATIVE_LAUNCHER), str(other)])
        self.assertFalse(any(
            call.args[0][0] == str(launcher.PDF_TARGET_VERIFIER)
            for call in run.call_args_list
        ))
        quarantine.assert_called_once()


if __name__ == "__main__":
    unittest.main()
