#!/usr/bin/env python3
"""Verify discovery-backed preference choices without touching user settings."""
import importlib.util
import subprocess
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("browser_preference_selector",
                                               ROOT / "browser_preference_selector.py")
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


class BrowserSelectorTests(unittest.TestCase):
    def test_discovery_populates_sorted_installed_options_only(self):
        rows = {"browsers": [
            {"bundle_id": "com.brave.Browser", "name": "Brave", "installed": True},
            {"bundle_id": "org.mozilla.firefox", "name": "Firefox", "installed": True},
            {"bundle_id": "com.google.Chrome", "name": "Chrome", "installed": True},
            {"bundle_id": "com.example.beta", "name": "Beta", "installed": False},
        ]}
        self.assertEqual(selector.selector_choices(rows), (
            ("Brave", "com.brave.Browser"), ("Chrome", "com.google.Chrome"),
            ("Firefox", "org.mozilla.firefox"),
        ))

    def test_multiple_installations_and_preview_channels(self):
        rows = [
            {"bundle_id": "com.brave.Browser", "name": "Brave Browser", "installed": True,
             "path": "/Applications/Brave Browser.app"},
            {"bundle_id": "com.brave.Browser", "name": "Brave", "installed": True,
             "path": "/Users/someone/Applications/Brave Browser.app"},
            {"bundle_id": "com.brave.Browser.beta", "name": "Brave Beta", "installed": True},
        ]
        self.assertEqual(selector.selector_choices(rows), (
            ("Brave", "com.brave.Browser"),
            ("Brave Beta", "com.brave.Browser.beta"),
        ))

    def test_invalid_unavailable_or_self_referential_entries_are_hidden(self):
        rows = [
            None, 3, {}, "Safari",
            {"bundle_id": "local.studio.brave-pdf-opener", "name": "Self", "installed": True},
            {"bundle_id": "com..invalid", "name": "Bad", "installed": True},
            {"bundle_id": "com.example.absent", "name": "Missing", "installed": False},
            {"bundle_id": "com.example.string", "name": "Wrong", "installed": "true"},
            {"bundle_id": "com.example.good", "name": "Unsafe\nRow", "installed": True},
        ]
        self.assertEqual(selector.selector_choices(rows),
                         (("com.example.good", "com.example.good"),))
        for invalid in (None, {}, {"browsers": {}}, "wrong", [None] * 2049):
            with self.subTest(value=type(invalid).__name__):
                with self.assertRaises(ValueError):
                    selector.selector_choices(invalid)

    def test_explicit_choice_current_marker_and_cancellation(self):
        choices = (("Brave", "com.brave.Browser"), ("Safari", "com.apple.Safari"))
        for answer, expected in (("1\n", "com.brave.Browser"),
                                 ("2\n", "com.apple.Safari"),
                                 ("\n", None), ("q\n", None), ("99\n", None),
                                 ("-1\n", None), ("2;danger\n", None)):
            with self.subTest(answer=answer):
                screen = StringIO()
                self.assertEqual(selector.choose_browser(choices,
                    current="com.apple.Safari", source=StringIO(answer),
                    destination=screen), expected)
                self.assertIn("Safari [com.apple.Safari] (current)", screen.getvalue())


    def test_marks_system_default_separately_from_current_preference(self):
        choices = (("Brave", "com.brave.Browser"),
                   ("Chrome", "com.google.Chrome"))
        for system_default, expected_markers in (
            ("com.google.Chrome", (
                "Brave [com.brave.Browser] (current)",
                "Chrome [com.google.Chrome] (system default)")),
            ("com.brave.Browser", (
                "Brave [com.brave.Browser] (current) (system default)",
                "Chrome [com.google.Chrome]")),
            ("com.example.not-installed", (
                "Brave [com.brave.Browser] (current)",
                "Chrome [com.google.Chrome]")),
            (None, (
                "Brave [com.brave.Browser] (current)",
                "Chrome [com.google.Chrome]")),
        ):
            with self.subTest(system_default=system_default):
                screen = StringIO()
                chosen = selector.choose_browser(
                    choices, current="com.brave.Browser",
                    system_default=system_default, source=StringIO("2\n"),
                    destination=screen)
                self.assertEqual(chosen, "com.google.Chrome")
                rows = screen.getvalue().splitlines()
                for marker in expected_markers:
                    self.assertIn(marker, rows[0] if marker.startswith("Brave") else rows[1])
                if system_default not in ("com.brave.Browser", "com.google.Chrome"):
                    self.assertNotIn("(system default)", screen.getvalue())

    def test_system_default_uses_read_only_resolver_and_fails_closed(self):
        resolver = Path("/fixed-test-path/resolve-default-browser")
        with patch.object(selector, "DEFAULT_BROWSER_RESOLVER", resolver):
            with patch.object(selector.subprocess, "run", return_value=(
                    subprocess.CompletedProcess([], 0, "com.apple.Safari\n", ""))) as run:
                self.assertEqual(selector.system_default_browser(), "com.apple.Safari")
                run.assert_called_once_with(
                    [str(resolver)], capture_output=True, text=True,
                    check=True, timeout=5)

            for output in ("", "com..bad", "local.studio.brave-pdf-opener",
                           "com.apple.Safari\ncom.brave.Browser",
                           "system-default-browser", "a" * 300):
                with self.subTest(output=output[:32]):
                    with patch.object(selector.subprocess, "run", return_value=(
                            subprocess.CompletedProcess([], 0, output, ""))):
                        self.assertIsNone(selector.system_default_browser())

            for failure in (FileNotFoundError("resolver not installed"),
                            subprocess.TimeoutExpired(str(resolver), 5),
                            subprocess.CalledProcessError(1, str(resolver))):
                with self.subTest(failure=type(failure).__name__):
                    with patch.object(selector.subprocess, "run", side_effect=failure):
                        self.assertIsNone(selector.system_default_browser())

    def test_empty_results_do_not_replace_saved_or_custom_selection(self):
        screen = StringIO()
        self.assertIsNone(selector.choose_browser((), current="com.example.custom",
                          source=StringIO("1\n"), destination=screen))
        self.assertIn("No installed browsers", screen.getvalue())

    def test_no_preference_file_access_or_browser_launch(self):
        choices = selector.selector_choices([{
            "bundle_id": "com.example.Browser", "name": "Example", "installed": True,
            "path": "/private/hidden/secret.app",
        }])
        with patch("builtins.open", side_effect=AssertionError("no file access")), \
                patch("subprocess.run", side_effect=AssertionError("no process launch")):
            self.assertEqual(selector.choose_browser(
                choices, source=StringIO("1\n"), destination=StringIO()),
                "com.example.Browser")


if __name__ == "__main__":
    unittest.main()
