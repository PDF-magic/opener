#!/usr/bin/env python3
"""Exercise Chromium PDF launching through the existing fail-closed scan gate."""

import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import file_launcher

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("chromium_scan_gate", ROOT / "scan-and-open.py")
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)

CHROMIUM_BUNDLE_ID = "org.chromium.Chromium"
DEFAULT_BUNDLE_ID = "com.brave.Browser"


class ChromiumLaunchingTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix="chromium-launch-")
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.setting = root / "target-app.txt"
        self.document = root / "Quarterly report – #1.PDF"
        self.document.write_bytes(b"%PDF-1.4\nChromium handoff")
        for obj, attr, value in (
            (file_launcher, "TARGET_APP_CONFIG", self.setting),
            (opener, "CACHE_DB", root / "clean-cache.sqlite3"),
            (opener, "SCAN_REQUEST_DB", root / "scan-requests.sqlite3"),
        ):
            mocked = patch.object(obj, attr, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        self.setting.write_text(CHROMIUM_BUNDLE_ID + "\n", encoding="ascii")
        # Do not let the optional scanner-version probe add a mocked scan call.
        version = patch.object(opener.subprocess, "check_output",
                               side_effect=FileNotFoundError)
        version.start()
        self.addCleanup(version.stop)

    def test_chromium_preflight_then_native_launch_after_clean_scan(self):
        calls = []

        def execute(command, **kwargs):
            if command[0] == "/scanner":
                calls.append("scan")
                return subprocess.CompletedProcess(command, 0, "document: OK\n", "")
            if command[0] == str(file_launcher.PDF_TARGET_VERIFIER):
                calls.append("verify")
            elif command[0] == str(file_launcher.NATIVE_LAUNCHER):
                calls.append("launch")
            return subprocess.CompletedProcess(command, 0, "", "")

        def remove(path):
            self.assertEqual(path, self.document)
            calls.append("quarantine")

        with patch.object(opener.subprocess, "run", side_effect=execute) as run, \
                patch.object(opener, "remove_quarantine", side_effect=remove):
            result = opener.scan_and_open(str(self.document), "/scanner")

        self.assertEqual(result.status, "clean")
        self.assertEqual(calls, ["scan", "verify", "quarantine", "launch"])
        commands = [item.args[0] for item in run.call_args_list]
        self.assertEqual(commands[0][0], "/scanner")
        self.assertIn("--alert-encrypted=yes", commands[0])
        self.assertEqual(commands[0][-2:], ["--", str(self.document)])
        self.assertEqual(commands[1], [str(file_launcher.PDF_TARGET_VERIFIER), CHROMIUM_BUNDLE_ID])
        proof = ":".join(map(str, opener.file_identity(self.document)[0][1:]))
        self.assertEqual(commands[2], [str(file_launcher.NATIVE_LAUNCHER),
                                       "--expected-identity", proof, "--bundle-id",
                                       CHROMIUM_BUNDLE_ID, str(self.document)])
        with sqlite3.connect(opener.SCAN_REQUEST_DB) as db:
            target = db.execute(
                "SELECT intended_destination_application FROM scan_requests"
            ).fetchone()
        self.assertEqual(target, (CHROMIUM_BUNDLE_ID,))
        self.assertEqual(self.document.read_bytes(), b"%PDF-1.4\nChromium handoff")
        self.assertEqual(self.setting.read_text(encoding="ascii"), CHROMIUM_BUNDLE_ID + "\n")

    def test_unregistered_chromium_pdf_handler_never_releases_quarantine(self):
        def execute(command, **kwargs):
            status = 1 if command[0] == str(file_launcher.PDF_TARGET_VERIFIER) else 0
            return subprocess.CompletedProcess(command, status, "document: OK", "")

        with patch.object(opener.subprocess, "run", side_effect=execute) as run, \
                patch.object(opener, "remove_quarantine") as remove:
            with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                opener.scan_and_open(self.document, "/scanner")
        commands = [item.args[0] for item in run.call_args_list]
        self.assertEqual([cmd[0] for cmd in commands],
                         ["/scanner", str(file_launcher.PDF_TARGET_VERIFIER)])
        remove.assert_not_called()

    def test_missing_chromium_verifier_fails_closed(self):
        def execute(command, **kwargs):
            if command[0] == str(file_launcher.PDF_TARGET_VERIFIER):
                raise FileNotFoundError("verifier unavailable")
            return subprocess.CompletedProcess(command, 0, "document: OK", "")

        with patch.object(opener.subprocess, "run", side_effect=execute) as run, \
                patch.object(opener, "remove_quarantine") as remove:
            with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                opener.scan_and_open(self.document, "/scanner")
        self.assertEqual(run.call_count, 2)
        remove.assert_not_called()

    def test_detected_malware_never_launches_chromium(self):
        infected = subprocess.CompletedProcess([], 1, "document: Example.Malware FOUND", "")
        with patch.object(opener.subprocess, "run", return_value=infected) as run, \
                patch.object(opener, "remove_quarantine") as remove:
            with self.assertRaisesRegex(RuntimeError, "Malware"):
                opener.scan_and_open(self.document, "/scanner")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][0], "/scanner")
        remove.assert_not_called()

    def test_chromium_destination_remains_pinned_if_config_changes_during_preflight(self):
        selected = []

        def preflight(path, target_app=None):
            selected.append(target_app)
            self.setting.write_text(DEFAULT_BUNDLE_ID + "\n", encoding="ascii")

        with patch.object(opener, "verify_launch_target", side_effect=preflight), \
                patch.object(opener.subprocess, "run",
                             return_value=subprocess.CompletedProcess([], 0, "document: OK", "")) as run, \
                patch.object(opener, "remove_quarantine"):
            opener.scan_and_open(self.document, "/scanner")
        self.assertEqual(selected, [CHROMIUM_BUNDLE_ID])
        proof = ":".join(map(str, opener.file_identity(self.document)[0][1:]))
        self.assertEqual(run.call_args.args[0],
                         [str(file_launcher.NATIVE_LAUNCHER), "--expected-identity", proof,
                          "--bundle-id", CHROMIUM_BUNDLE_ID, str(self.document)])

    def test_existing_brave_default_is_unchanged(self):
        self.setting.unlink()
        self.assertEqual(file_launcher.pdf_target_application(), DEFAULT_BUNDLE_ID)


if __name__ == "__main__":
    unittest.main()
