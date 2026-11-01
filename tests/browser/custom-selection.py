#!/usr/bin/env python3
"""Exercise custom PDF browser selection and the real scanner handoff contract.

All external tools are mocked; only temporary settings and files are used.
"""
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
import file_launcher as launcher

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chooser = load("custom_browser_chooser_test", "select-custom-pdf-application.py")
opener = load("custom_browser_scan_test", "scan-and-open.py")


class CustomBrowserSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="opener-custom-browser-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pdf = self.root / "Selected document.PDF"
        self.pdf.write_bytes(b"%PDF-1.4\nCustom browser test fixture\n")
        self.setting = self.root / "target-app.txt"
        self.setting.write_text("com.brave.Browser\n")
        self.custom = "org.example.CustomPDFBrowser"
        self.application = "/Applications/Custom Browser.app"
        self.events = []
        self.picker_code = 0
        self.picker_output = (self.custom + "\n").encode("ascii")
        self.selection_verifier_code = 0
        self.launch_verifier_code = 0
        self.scanner_code = 0
        self.verify_count = 0

        for obj, attribute, value in (
            (launcher, "TARGET_APP_CONFIG", self.setting),
            (launcher, "FALLBACK_APP_CONFIG", self.root / "absent-fallback.txt"),
            (opener, "CACHE_DB", self.root / "cache.sqlite3"),
            (opener, "SCAN_REQUEST_DB", self.root / "requests.sqlite3"),
        ):
            control = patch.object(obj, attribute, value)
            control.start()
            self.addCleanup(control.stop)
        # Keep production parsing, verifier ordering and scan-request tracking;
        # replace only external executable invocations and quarantine mutation.
        for obj, attribute, callback in (
            (subprocess, "run", self.run_command),
            (launcher, "require_executable_path", lambda *args, **kwargs: None),
            (opener, "remove_quarantine", self.remove_quarantine),
        ):
            control = patch.object(obj, attribute, side_effect=callback)
            control.start()
            self.addCleanup(control.stop)

    def remove_quarantine(self, path):
        self.events.append(("quarantine", path))

    def run_command(self, args, **kwargs):
        command = args[0]
        if command == str(chooser.NATIVE_PICKER):
            self.events.append(("picker", args))
            return subprocess.CompletedProcess(args, self.picker_code, self.picker_output, b"")
        if command == str(launcher.PDF_TARGET_VERIFIER):
            self.verify_count += 1
            self.events.append(("verify", args))
            code = (self.selection_verifier_code if self.verify_count == 1
                    else self.launch_verifier_code)
            return subprocess.CompletedProcess(args, code, b"", b"")
        if command == "/scanner":
            if args[1:] == ["--version"]:
                return subprocess.CompletedProcess(args, 0, "ClamAV 1.4.0/1", "")
            self.events.append(("scan", args))
            return subprocess.CompletedProcess(
                args, self.scanner_code,
                "file: Malware FOUND" if self.scanner_code else "file: OK", "")
        if command == str(launcher.NATIVE_LAUNCHER):
            self.events.append(("open", args))
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(f"Unexpected subprocess: {command}")

    def stages(self):
        return [name for name, _ in self.events]

    def select_custom(self):
        self.assertEqual(chooser.choose_and_save(self.application, self.setting), self.custom)
        self.assertEqual(self.setting.read_text(), self.custom + "\n")

    def test_selected_custom_browser_is_reverified_after_clean_scan(self):
        self.select_custom()
        self.assertEqual(self.stages(), ["picker", "verify"])
        self.assertEqual(self.events[0][1],
                         [str(chooser.NATIVE_PICKER), "--application", self.application])
        self.assertEqual(self.events[1][1],
                         [str(launcher.PDF_TARGET_VERIFIER), self.custom])
        self.assertEqual(launcher.pdf_target_application(), self.custom)

        outcome = opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(outcome.status, "clean")
        self.assertEqual(self.stages(),
                         ["picker", "verify", "scan", "verify", "quarantine", "open"])
        self.assertIn("--alert-encrypted=yes", self.events[2][1])
        self.assertEqual(self.events[3][1],
                         [str(launcher.PDF_TARGET_VERIFIER), self.custom])
        proof = ":".join(map(str, opener.file_identity(self.pdf)[0][1:]))
        self.assertEqual(self.events[5][1], [
            str(launcher.NATIVE_LAUNCHER), "--expected-identity", proof,
            "--bundle-id", self.custom, str(self.pdf)])
        with sqlite3.connect(opener.SCAN_REQUEST_DB) as db:
            targets = [row[0] for row in db.execute(
                "SELECT intended_destination_application FROM scan_requests")]
        self.assertEqual(targets, [self.custom])
        self.assertEqual(self.setting.read_text(), self.custom + "\n")

    def test_cancellation_and_invalid_identity_leave_prior_browser_untouched(self):
        for code, output in (
            (1, (self.custom + "\n").encode("ascii")),
            (0, b"local.studio.brave-pdf-opener\n"),
            (0, b"com.brave.Browser\norg.example.other\n"),
        ):
            with self.subTest(code=code, output=output):
                self.picker_code, self.picker_output = code, output
                self.events.clear()
                with self.assertRaises(RuntimeError):
                    chooser.choose_and_save(self.application, self.setting)
                self.assertEqual(self.setting.read_text(), "com.brave.Browser\n")
                self.assertNotIn("scan", self.stages())
                self.assertNotIn("open", self.stages())
        self.assertEqual(launcher.pdf_target_application(), "com.brave.Browser")

    def test_failed_selection_verifier_never_saves_custom_browser(self):
        self.selection_verifier_code = 1
        with self.assertRaisesRegex(RuntimeError, "cannot be verified"):
            chooser.choose_and_save(self.application, self.setting)
        self.assertEqual(self.stages(), ["picker", "verify"])
        self.assertEqual(self.setting.read_text(), "com.brave.Browser\n")

    def test_removed_custom_browser_fails_closed_after_scan(self):
        self.select_custom()
        self.launch_verifier_code = 1
        with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
            opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(self.stages(), ["picker", "verify", "scan", "verify"])
        self.assertEqual(self.setting.read_text(), self.custom + "\n")

    def test_malware_blocks_selected_custom_browser_without_opening(self):
        self.select_custom()
        self.scanner_code = 1
        with self.assertRaisesRegex(RuntimeError, "Malware"):
            opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(self.stages(), ["picker", "verify", "scan"])
        self.assertEqual(self.setting.read_text(), self.custom + "\n")


if __name__ == "__main__":
    unittest.main(verbosity=2)
