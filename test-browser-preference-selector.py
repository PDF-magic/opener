#!/usr/bin/env python3
"""Verify discovery-backed preference choices without touching user settings."""
import importlib.util
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

    def test_empty_results_do_not_replace_saved_or_custom_selection(self):
        screen = StringIO()
        self.assertIsNone(selector.choose_browser((), current="com.example.custom",
                          source=StringIO("1\n"), destination=screen))
        self.assertIn("No installed browsers", screen.getvalue())

    def test_additional_applications_are_hidden_until_explicitly_requested(self):
        browsers = (("Brave", "com.brave.Browser"), ("Safari", "com.apple.Safari"))
        payload = {"browsers": [
            {"bundle_id": "com.brave.Browser", "name": "Brave", "installed": True},
            {"bundle_id": "com.apple.Safari", "name": "Safari", "installed": True},
        ], "applications": [
            {"bundleIdentifier": "org.example.Reader", "name": "PDF Reader",
             "path": "/Applications/Reader.app"},
            {"bundleIdentifier": "com.brave.Browser", "name": "Brave",
             "path": "/Applications/Brave.app"},
            {"bundle_id": "org.example.Editor", "name": "Editor", "installed": True},
            {"bundle_id": "org.example.Editor", "name": "Extra Editor", "installed": True},
            {"bundle_id": "org.example.hidden", "name": "Not Installed", "installed": False},
            {"bundle_id": "local.studio.brave-pdf-opener", "name": "Opener",
             "installed": True},
            {"bundle_id": "org.example.bad", "name": "Hidden\nApplication",
             "installed": True},
            {"bundleIdentifier": "org.example.fake", "name": "Not Verified",
             "path": "relative/Reader.app"},
        ]}
        extras = selector.additional_application_choices(payload, browsers)
        self.assertEqual(extras, (("Editor", "org.example.Editor"),
                                  ("org.example.bad", "org.example.bad"),
                                  ("PDF Reader", "org.example.Reader")))
        hidden = StringIO()
        self.assertEqual(selector.choose_browser(
            browsers, current="com.apple.Safari",
            additional_choices=extras, source=StringIO("2\n"),
            destination=hidden), "com.apple.Safari")
        self.assertIn("a. Show additional installed applications", hidden.getvalue())
        self.assertNotIn("PDF Reader [org.example.Reader]", hidden.getvalue())
        self.assertIn("Safari [com.apple.Safari] (current)", hidden.getvalue())

        shown = StringIO()
        self.assertEqual(selector.choose_browser(
            browsers, current="com.apple.Safari",
            additional_choices=extras, source=StringIO("a\n2\n"),
            destination=shown), "com.apple.Safari")
        self.assertIn("Additional installed applications (view only):", shown.getvalue())
        self.assertIn("PDF Reader [org.example.Reader]", shown.getvalue())
        self.assertIn("a. Hide additional installed applications", shown.getvalue())
        self.assertIn("Safari [com.apple.Safari] (current)", shown.getvalue())
        self.assertNotIn("/Applications/Reader.app", shown.getvalue())

    def test_extra_applications_never_become_selectable_browser_choices(self):
        choices = (("Brave", "com.brave.Browser"),)
        extras = (("Editor", "org.example.Editor"),)
        for answer, expected in (("a\n2\n", None),
                                 ("a\nq\n", None),
                                 ("a\n1\n", "com.brave.Browser"),
                                 ("a\na\n\n", None)):
            with self.subTest(answer=answer):
                screen = StringIO()
                self.assertEqual(selector.choose_browser(
                    choices, additional_choices=extras,
                    source=StringIO(answer), destination=screen), expected)
        self.assertEqual(selector.additional_application_choices(
            [{"bundle_id": "org.example.Editor", "name": "Editor",
              "installed": True}], choices), ())
        for bad in ({"applications": {}}, {"applications": [None] * 2049}):
            with self.assertRaises(ValueError):
                selector.additional_application_choices(bad, choices)

    def test_no_additional_applications_does_not_trigger_discovery_or_save(self):
        choices = (("Brave", "com.brave.Browser"),)
        screen = StringIO()
        with patch("builtins.open", side_effect=AssertionError("no file access")), \
                patch("subprocess.run", side_effect=AssertionError("no process launch")):
            self.assertEqual(selector.choose_browser(
                choices, additional_choices=(), source=StringIO("a\n1\n"),
                destination=screen), "com.brave.Browser")
        self.assertIn("No additional installed applications", screen.getvalue())

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
