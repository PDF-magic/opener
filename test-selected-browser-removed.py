#!/usr/bin/env python3
"""Verify a removed selected PDF browser blocks launching without replacing the saved choice."""
import importlib.util
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import browser_preference_selector as selector
import file_launcher as launcher

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("removed_browser_scanner", ROOT / "scan-and-open.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)


class RemovedSelectedBrowserTests(unittest.TestCase):
    def test_selected_browser_removed_blocks_pdf_launch_without_fallback(self):
        with tempfile.TemporaryDirectory(prefix="opener-removed-0159-") as directory:
            root = Path(directory)
            chosen = "com.brave.Browser"
            app = root / "Brave Browser.app"
            app.mkdir()
            other = root / "Safari.app"
            other.mkdir()
            saved = root / "target-app.txt"
            saved.write_text(chosen + "\n", encoding="ascii")
            pdf = root / "approved.PDF"
            pdf.write_bytes(b"%PDF-1.4\nsynthetic safe fixture")
            commands = []
            def execute(command, *args, **kwargs):
                commands.append(command)
                if command[0] == str(launcher.PDF_TARGET_VERIFIER):
                    return subprocess.CompletedProcess(command, 0 if app.exists() else 1, b"", b"")
                if command[0] == "/scanner":
                    return subprocess.CompletedProcess(command, 0, "document: OK", "")
                raise AssertionError("No native launch, setting mutation, or fallback is permitted")

            with patch.object(launcher, "TARGET_APP_CONFIG", saved), \
                    patch.object(launcher, "FALLBACK_APP_CONFIG", root / "missing-fallback.txt"), \
                    patch.object(scanner, "CACHE_DB", root / "cache.sqlite3"), \
                    patch.object(scanner, "SCAN_REQUEST_DB", root / "requests.sqlite3"), \
                    patch.object(scanner, "scanner_path", return_value="/scanner"), \
                    patch.object(scanner, "check_database"), \
                    patch.object(scanner, "remove_quarantine") as quarantine, \
                    patch.object(scanner.subprocess, "run", side_effect=execute), \
                    patch("sys.stderr", new_callable=StringIO) as diagnostics:
                self.assertEqual(launcher.pdf_target_application(), chosen)
                launcher.verify_launch_target(pdf, target_app=chosen)
                self.assertEqual(commands[-1], [str(launcher.PDF_TARGET_VERIFIER), chosen])
                commands.clear()
                app.rmdir()  # Selected browser removed while Safari remains.
                self.assertTrue(other.is_dir())
                discovered = selector.selector_choices([
                    {"bundle_id": chosen, "name": "Brave", "installed": False},
                    {"bundle_id": "com.apple.Safari", "name": "Safari", "installed": True},
                ])
                self.assertEqual(discovered, (("Safari", "com.apple.Safari"),))
                self.assertEqual(selector.saved_browser_preference(saved), chosen)
                self.assertEqual(launcher.pdf_target_application(), chosen)
                screen = StringIO()
                self.assertIsNone(selector.choose_browser(
                    discovered, current=selector.saved_browser_preference(saved),
                    source=StringIO("q\n"), destination=screen))
                self.assertNotIn("(current)", screen.getvalue())
                self.assertEqual(scanner.main([str(pdf)]), 1)
                self.assertIn("selected PDF application is unavailable", diagnostics.getvalue())
                self.assertEqual(commands[-1], [str(launcher.PDF_TARGET_VERIFIER), chosen])
                self.assertFalse(any(str(launcher.NATIVE_LAUNCHER) == c[0] for c in commands))
                self.assertFalse(any("com.apple.Safari" in c for c in commands))
                quarantine.assert_not_called()
                self.assertEqual(saved.read_text(encoding="ascii"), chosen + "\n")
                self.assertNotIn(str(pdf), diagnostics.getvalue())


if __name__ == "__main__":
    unittest.main()
