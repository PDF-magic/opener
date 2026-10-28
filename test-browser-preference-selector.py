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

    def test_multiple_installations_deduplicate_and_unsupported_preview_hidden(self):
        rows = [
            {"bundle_id": "com.brave.Browser", "name": "Brave Browser", "installed": True,
             "path": "/Applications/Brave Browser.app"},
            {"bundle_id": "com.brave.Browser", "name": "Brave", "installed": True,
             "path": "/Users/someone/Applications/Brave Browser.app"},
            {"bundle_id": "com.brave.Browser.beta", "name": "Brave Beta", "installed": True},
        ]
        self.assertEqual(selector.selector_choices(rows),
                         (("Brave", "com.brave.Browser"),))

    def test_invalid_unavailable_or_self_referential_entries_are_hidden(self):
        rows = [
            None, 3, {}, "Safari",
            {"bundle_id": "local.studio.brave-pdf-opener", "name": "Self", "installed": True},
            {"bundle_id": "com..invalid", "name": "Bad", "installed": True},
            {"bundle_id": "com.example.absent", "name": "Missing", "installed": False},
            {"bundle_id": "com.example.string", "name": "Wrong", "installed": "true"},
            {"bundle_id": "com.apple.Safari", "name": "Unsafe\nRow", "installed": True},
        ]
        self.assertEqual(selector.selector_choices(rows),
                         (("com.apple.Safari", "com.apple.Safari"),))
        for invalid in (None, {}, {"browsers": {}}, "wrong", [None] * 2049):
            with self.subTest(value=type(invalid).__name__):
                with self.assertRaises(ValueError):
                    selector.selector_choices(invalid)

    def test_primary_list_contains_only_exact_supported_registry_identifiers(self):
        from browser_registry import SUPPORTED_BROWSER_BUNDLE_IDS

        rows = [{"bundle_id": bundle_id, "name": bundle_id, "installed": True}
                for bundle_id in SUPPORTED_BROWSER_BUNDLE_IDS]
        rows.extend([
            {"bundle_id": "com.brave.Browser.beta", "name": "Brave Beta",
             "installed": True},
            {"bundle_id": "com.google.Chrome.dev", "name": "Chrome Dev",
             "installed": True},
            {"bundle_id": "com.apple.SafariTechnologyPreview",
             "name": "Safari Technology Preview", "installed": True},
            {"bundle_id": "com.brave.Browser.fake", "name": "Brave",
             "installed": True},
            {"bundle_id": "org.example.CustomBrowser", "name": "Custom",
             "installed": True},
        ])
        choices = selector.selector_choices(rows)
        self.assertEqual({bundle_id for _, bundle_id in choices},
                         SUPPORTED_BROWSER_BUNDLE_IDS)
        self.assertEqual(len(choices), len(SUPPORTED_BROWSER_BUNDLE_IDS))

    def test_discovery_claims_cannot_override_support_and_custom_current_is_not_replaced(self):
        discovered = [
            {"bundle_id": "org.example.Unknown", "name": "Unknown",
             "installed": True, "supported": True, "pdf_capable": True},
            {"bundle_id": "org.mozilla.firefox.untrusted", "name": "Firefox",
             "installed": True, "supported": True},
            {"bundle_id": "com.apple.Safari", "name": "Safari", "installed": True},
        ]
        choices = selector.selector_choices(discovered)
        self.assertEqual(choices, (("Safari", "com.apple.Safari"),))
        screen = StringIO()
        self.assertIsNone(selector.choose_browser(
            choices, current="org.example.Custom", source=StringIO("\n"),
            destination=screen))
        self.assertNotIn("org.example.Custom", screen.getvalue())
        self.assertNotIn("org.example.Unknown", screen.getvalue())
        self.assertIn("Safari", screen.getvalue())

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

    def test_no_preference_file_access_or_browser_launch(self):
        choices = selector.selector_choices([{
            "bundle_id": "com.apple.Safari", "name": "Safari", "installed": True,
            "path": "/private/hidden/secret.app",
        }])
        with patch("builtins.open", side_effect=AssertionError("no file access")), \
                patch("subprocess.run", side_effect=AssertionError("no process launch")):
            self.assertEqual(selector.choose_browser(
                choices, source=StringIO("1\n"), destination=StringIO()),
                "com.apple.Safari")


if __name__ == "__main__":
    unittest.main()
