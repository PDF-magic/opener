#!/usr/bin/env python3
"""Verify each browser-specific PDF handoff without requiring installed browsers."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import file_launcher as launcher

sys.dont_write_bytecode = True
BROWSERS = {
    "brave": "com.brave.Browser",
    "chrome": "com.google.Chrome",
    "firefox": "org.mozilla.firefox",
    "safari": "com.apple.Safari",
    "edge": "com.microsoft.edgemac",
    "chromium": "org.chromium.Chromium",
    "vivaldi": "com.vivaldi.Vivaldi",
    "opera": "com.operasoftware.Opera",
    "arc": "company.thebrowser.Browser",
}
selected = os.environ.get("PDF_MAGIC_TEST_BROWSER")
if selected not in BROWSERS:
    raise SystemExit("Select one PDF_MAGIC_TEST_BROWSER: " + ", ".join(BROWSERS))

source = Path(__file__).with_name("scan-and-open.py")
spec = importlib.util.spec_from_file_location("browser_pdf_scan", source)
opener = importlib.util.module_from_spec(spec)
spec.loader.exec_module(opener)


class PerBrowserPDFTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.pdf = root / "Selected report – 2026.PDF"
        self.pdf.write_bytes(b"%PDF-1.4\nSample\n")
        self.setting = root / "target-app.txt"
        self.bundle = BROWSERS[selected]
        self.setting.write_text(self.bundle + "\n")
        for obj, name, value in (
            (launcher, "TARGET_APP_CONFIG", self.setting),
            (opener, "CACHE_DB", root / "cache.sqlite3"),
            (opener, "SCAN_REQUEST_DB", root / "requests.sqlite3"),
        ):
            p = patch.object(obj, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.events = []
        self.scanner_code = 0
        self.verifier_code = 0
        self.verifier_error = None
        self.fail_launch = False
        self.swap_preference = False
        for obj, name, callback in (
            (opener.subprocess, "run", self.run_command),
            (opener, "remove_quarantine", self.remove_quarantine),
        ):
            p = patch.object(obj, name, side_effect=callback)
            p.start()
            self.addCleanup(p.stop)

    def remove_quarantine(self, path):
        self.events.append(("quarantine", path))

    def run_command(self, args, **kwargs):
        command = args[0]
        if command == "/scanner":
            self.events.append(("scan", args))
            return subprocess.CompletedProcess(
                args, self.scanner_code,
                "file: Malware FOUND" if self.scanner_code else "file: OK", "")
        if command == str(launcher.PDF_TARGET_VERIFIER):
            self.events.append(("verify", args))
            if self.swap_preference:
                self.setting.write_text("com.apple.Preview\n")
            if self.verifier_error is not None:
                raise self.verifier_error
            return subprocess.CompletedProcess(args, self.verifier_code, "", "")
        if command == str(launcher.NATIVE_LAUNCHER):
            self.events.append(("open", args))
            if self.fail_launch:
                raise subprocess.CalledProcessError(1, args)
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError("Unexpected process during PDF handoff")

    def stages(self):
        return [kind for kind, _ in self.events]

    def assert_browser_opened(self):
        self.assertEqual(self.stages(), ["scan", "verify", "quarantine", "open"])
        self.assertEqual(self.events[0][1][0], "/scanner")
        self.assertIn("--alert-encrypted=yes", self.events[0][1])
        self.assertEqual(self.events[0][1][-1], str(self.pdf))
        self.assertEqual(self.events[1][1],
                         [str(launcher.PDF_TARGET_VERIFIER), self.bundle])
        self.assertEqual(self.events[2][1], self.pdf)
        self.assertEqual(self.events[3][1],
                         [str(launcher.NATIVE_LAUNCHER), "--bundle-id",
                          self.bundle, str(self.pdf)])

    def test_clean_pdf_is_scanned_and_opened_in_the_selected_browser(self):
        self.assertEqual(launcher.pdf_target_application(), self.bundle)
        result = opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(result.status, "clean")
        self.assert_browser_opened()
        with sqlite3.connect(opener.SCAN_REQUEST_DB) as db:
            destination = db.execute(
                "SELECT intended_destination_application FROM scan_requests"
            ).fetchone()
        self.assertEqual(destination, (self.bundle,))

    def test_unverified_browser_never_opens_or_releases_quarantine(self):
        self.verifier_code = 1
        with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
            opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(self.stages(), ["scan", "verify"])

    def test_missing_verifier_never_opens(self):
        self.verifier_error = FileNotFoundError("missing verifier")
        with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
            opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(self.stages(), ["scan", "verify"])

    def test_timed_out_verifier_never_opens(self):
        self.verifier_error = subprocess.TimeoutExpired("verifier", 10)
        with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
            opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(self.stages(), ["scan", "verify"])

    def test_malware_prevents_verification_quarantine_and_opening(self):
        self.scanner_code = 1
        with self.assertRaisesRegex(RuntimeError, "Malware"):
            opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(self.stages(), ["scan"])

    def test_changing_preference_does_not_redirect_approved_pdf(self):
        self.swap_preference = True
        result = opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(result.status, "clean")
        self.assert_browser_opened()
        self.assertEqual(self.setting.read_text(), "com.apple.Preview\n")

    def test_browser_launch_failure_preserves_clean_scan_verdict(self):
        self.fail_launch = True
        with self.assertRaises(opener.LaunchFailedError) as caught:
            opener.scan_and_open(str(self.pdf), "/scanner")
        self.assertEqual(caught.exception.scan_result.status, "clean")
        self.assert_browser_opened()


if __name__ == "__main__":
    unittest.main(verbosity=2)
