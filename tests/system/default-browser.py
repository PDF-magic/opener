#!/usr/bin/env python3
"""Verify the opt-in HTTPS default browser is pinned behind the existing PDF scan gate."""
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
spec = importlib.util.spec_from_file_location("scanner_for_default_browser", ROOT / "scan-and-open.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class SystemDefaultBrowserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.document = self.root / "report – final.PDF"
        self.document.write_bytes(b"%PDF-1.4\nsafe fixture")
        self.settings = self.root / "target-app.txt"
        self.settings.write_text("system-default-browser\n")
        for obj, field, path in (
            (launcher, "TARGET_APP_CONFIG", self.settings),
            (scanner, "CACHE_DB", self.root / "cache.sqlite3"),
            (scanner, "SCAN_REQUEST_DB", self.root / "requests.sqlite3"),
        ):
            control = patch.object(obj, field, path)
            control.start()
            self.addCleanup(control.stop)

    def test_pins_selected_browser_through_scan_preflight_and_launch(self):
        commands = []

        def execute(command, *args, **kwargs):
            commands.append(command)
            if command == [str(launcher.DEFAULT_BROWSER_RESOLVER)]:
                self.assertEqual(kwargs, {"capture_output": True, "timeout": 10, "check": True})
                return subprocess.CompletedProcess(command, 0, b"com.apple.Safari\n", b"")
            if command[0] == "/scanner":
                return subprocess.CompletedProcess(command, 0, "document: OK", "")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with patch.object(scanner.subprocess, "run", side_effect=execute), \
                patch.object(scanner, "remove_quarantine") as quarantine:
            scanner.scan_and_open(str(self.document), "/scanner")
        self.assertEqual(commands[0], [str(launcher.DEFAULT_BROWSER_RESOLVER)])
        self.assertEqual(commands[1][0], "/scanner")
        preflight = [str(launcher.PDF_TARGET_VERIFIER), "com.apple.Safari"]
        launch = [str(launcher.NATIVE_LAUNCHER), "--bundle-id",
                  "com.apple.Safari", str(self.document)]
        self.assertIn(preflight, commands)
        self.assertEqual(commands[-1], launch)
        self.assertLess(commands.index(preflight), commands.index(launch))
        self.assertEqual(commands.count([str(launcher.DEFAULT_BROWSER_RESOLVER)]), 1)
        with sqlite3.connect(scanner.SCAN_REQUEST_DB) as db:
            selected = db.execute(
                "SELECT intended_destination_application FROM scan_requests"
            ).fetchone()
        self.assertEqual(selected, ("com.apple.Safari",))
        quarantine.assert_called_once()

    def test_unresolvable_browser_fails_before_scanning_or_quarantine(self):
        invalid = [b"", b"no-browser", b"com..browser\n",
                   b"local.studio.brave-pdf-opener\n", b"com.apple.Safari\ncom.google.Chrome",
                   b"\xff", b"com.apple.Safari;unexpected"]
        for response in invalid:
            with self.subTest(response=response):
                completed = subprocess.CompletedProcess([], 0, response, b"")
                with patch.object(scanner.subprocess, "run", return_value=completed) as run, \
                        patch.object(scanner, "remove_quarantine") as quarantine:
                    with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                        scanner.scan_and_open(str(self.document), "/scanner")
                run.assert_called_once()
                quarantine.assert_not_called()

        for failure in (FileNotFoundError("missing native helper"),
                        subprocess.TimeoutExpired("resolver", 10),
                        subprocess.CalledProcessError(1, "resolver")):
            with self.subTest(failure=type(failure).__name__):
                with patch.object(scanner.subprocess, "run", side_effect=failure) as run, \
                        patch.object(scanner, "remove_quarantine") as quarantine:
                    with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                        scanner.scan_and_open(str(self.document), "/scanner")
                run.assert_called_once()
                quarantine.assert_not_called()

    def test_missing_system_default_browser_displays_recovery_instructions(self):
        from io import StringIO

        diagnostics = StringIO()
        with patch.object(scanner, "scanner_path", return_value="/scanner"), \
                patch.object(scanner, "check_database"), \
                patch.object(scanner.subprocess, "run",
                             side_effect=FileNotFoundError("/private/secret/resolver")) as run, \
                patch.object(scanner, "remove_quarantine") as quarantine, \
                patch("sys.stderr", diagnostics):
            self.assertEqual(scanner.main([str(self.document)]), 1)
        self.assertIn("default browser is unavailable", diagnostics.getvalue())
        self.assertIn("System Settings", diagnostics.getvalue())
        self.assertIn("target-app.txt", diagnostics.getvalue())
        self.assertNotIn("/private/secret", diagnostics.getvalue())
        self.assertNotIn(str(self.document), diagnostics.getvalue())
        run.assert_called_once()
        quarantine.assert_not_called()

    def test_unsupported_default_browser_never_reaches_launch(self):
        commands = []

        def execute(command, *args, **kwargs):
            commands.append(command)
            if command[0] == str(launcher.DEFAULT_BROWSER_RESOLVER):
                return subprocess.CompletedProcess(command, 0, b"com.example.Browser\n", b"")
            if command[0] == "/scanner":
                return subprocess.CompletedProcess(command, 0, "document: OK", "")
            return subprocess.CompletedProcess(command, 1, b"", b"")

        with patch.object(scanner.subprocess, "run", side_effect=execute), \
                patch.object(scanner, "remove_quarantine") as quarantine:
            with self.assertRaisesRegex(RuntimeError, "opening was stopped"):
                scanner.scan_and_open(str(self.document), "/scanner")
        self.assertIn([str(launcher.PDF_TARGET_VERIFIER), "com.example.Browser"], commands)
        self.assertFalse(any(cmd[0] == str(launcher.NATIVE_LAUNCHER) for cmd in commands))
        quarantine.assert_not_called()

    def test_non_pdf_does_not_resolve_browser(self):
        path = self.root / "notes.txt"
        path.write_text("hello")
        with patch.object(launcher.subprocess, "run") as run:
            launcher.launch_clean_file(path)
        run.assert_called_once_with([str(launcher.NATIVE_LAUNCHER), str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
