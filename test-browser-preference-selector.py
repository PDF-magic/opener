#!/usr/bin/env python3
"""Verify discovery-backed preference choices without touching user settings."""
import importlib.util
import subprocess
import tempfile
from io import StringIO
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("browser_preference_selector",
                                               ROOT / "browser_preference_selector.py")
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)

picker_spec = importlib.util.spec_from_file_location(
    "select_custom_pdf_application", ROOT / "select-custom-pdf-application.py")
picker = importlib.util.module_from_spec(picker_spec)
picker_spec.loader.exec_module(picker)


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

    def test_multiple_installations_and_unsupported_preview_hidden(self):
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

    def test_primary_list_requires_exact_supported_registry_membership(self):
        from browser_registry import SUPPORTED_BROWSER_BUNDLE_IDS

        rows = [{"bundle_id": identifier, "name": identifier, "installed": True}
                for identifier in SUPPORTED_BROWSER_BUNDLE_IDS]
        rows += [
            {"bundle_id": "com.brave.Browser.beta", "name": "Brave Beta",
             "installed": True, "supported": True},
            {"bundle_id": "com.google.Chrome.dev", "name": "Chrome Dev",
             "installed": True},
            {"bundle_id": "com.apple.SafariTechnologyPreview",
             "name": "Safari Preview", "installed": True},
            {"bundle_id": "org.mozilla.firefox.spoof", "name": "Firefox",
             "installed": True},
            {"bundle_id": "org.example.Custom", "name": "Custom",
             "installed": True, "pdf_capable": True},
        ]
        choices = selector.selector_choices(rows)
        self.assertEqual({identifier for _, identifier in choices},
                         SUPPORTED_BROWSER_BUNDLE_IDS)
        self.assertEqual(len(choices), len(SUPPORTED_BROWSER_BUNDLE_IDS))

    def test_unknown_current_and_default_do_not_insert_unsupported_options(self):
        choices = selector.selector_choices([
            {"bundle_id": "com.apple.Safari", "name": "Safari", "installed": True},
            {"bundle_id": "com.example.Custom", "name": "Custom", "installed": True},
        ])
        screen = StringIO()
        self.assertIsNone(selector.choose_browser(
            choices, current="com.example.Custom",
            system_default="com.example.Custom", source=StringIO("\n"),
            destination=screen))
        self.assertEqual(choices, (("Safari", "com.apple.Safari"),))
        self.assertNotIn("com.example.Custom", screen.getvalue())
        self.assertNotIn("(system default)", screen.getvalue())

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

    def test_saved_selection_survives_repeated_selector_restarts(self):
        # Exercise the existing atomic preference writer and independent
        # selector reads rather than inventing a second storage location.
        with tempfile.TemporaryDirectory(prefix="opener-restore-") as directory:
            setting = Path(directory) / "target-app.txt"
            self.assertEqual(selector.saved_browser_preference(setting),
                             "com.brave.Browser")
            choices = (("Brave", "com.brave.Browser"),
                       ("Chrome", "com.google.Chrome"),
                       ("Safari", "com.apple.Safari"))
            for saved in ("com.apple.Safari", "com.google.Chrome"):
                picker.persist_preference(saved, setting)
                for _ in range(2):
                    # Each call stands in for opening a new selector process.
                    current = selector.saved_browser_preference(setting)
                    self.assertEqual(current, saved)
                    screen = StringIO()
                    self.assertIsNone(selector.choose_browser(
                        choices, current=current, source=StringIO("q\n"),
                        destination=screen))
                    self.assertIn(f"[{saved}] (current)", screen.getvalue())
                    self.assertEqual(setting.read_text(), saved + "\n")
            # A custom saved choice outside the primary list is preserved
            # even if the browser isn't in the discovered results.
            picker.persist_preference("org.example.customBrowser", setting)
            self.assertEqual(selector.saved_browser_preference(setting),
                             "org.example.customBrowser")
            screen = StringIO()
            selector.choose_browser(choices, current=selector.saved_browser_preference(setting),
                                    source=StringIO("q\n"), destination=screen)
            self.assertNotIn("(current)", screen.getvalue())
            self.assertEqual(setting.read_text(), "org.example.customBrowser\n")

    def test_selector_automatically_restores_current_or_honors_explicit_override(self):
        class Input:
            def __init__(self, payload):
                self.buffer = __import__("io").BytesIO(payload)

        payload = b'{"browsers":[{"bundle_id":"com.apple.Safari","name":"Safari","installed":true}]}'
        for args, expected, should_load in (
            ([], "com.apple.Safari", True),
            (["--current", "com.brave.Browser"], "com.brave.Browser", False),
        ):
            with self.subTest(args=args), \
                    patch.object(selector.sys, "stdin", Input(payload)), \
                    patch("builtins.open", return_value=StringIO("q\n")), \
                    patch.object(selector, "saved_browser_preference",
                                 return_value="com.apple.Safari") as load, \
                    patch.object(selector, "system_default_browser", return_value=None), \
                    patch.object(selector, "choose_browser", return_value=None) as show:
                self.assertEqual(selector.main(args), 1)
                self.assertEqual(show.call_args.kwargs["current"], expected)
                self.assertEqual(load.call_count, 1 if should_load else 0)

    def test_saved_preference_bad_files_fail_closed_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix="opener-restore-") as directory:
            setting = Path(directory) / "target-app.txt"
            for invalid in ("", "bad-id", "org..broken", "local.studio.brave-pdf-opener",
                            "system-default-browser", "com.apple.Safari\ncom.google.Chrome",
                            "x" * 260):
                with self.subTest(invalid=invalid[:24]):
                    setting.write_text(invalid)
                    self.assertIsNone(selector.saved_browser_preference(setting))
                    self.assertEqual(setting.read_text(), invalid)
            setting.write_bytes(b"bad\xff")
            self.assertIsNone(selector.saved_browser_preference(setting))
            self.assertEqual(setting.read_bytes(), b"bad\xff")
            setting.unlink()
            other = Path(directory) / "unrelated.txt"
            other.write_text("com.apple.Safari\n")
            setting.symlink_to(other)
            self.assertIsNone(selector.saved_browser_preference(setting))
            self.assertEqual(other.read_text(), "com.apple.Safari\n")
            setting.unlink()
            setting.mkdir()
            self.assertIsNone(selector.saved_browser_preference(setting))
            setting.rmdir()
            alias = Path(directory) / "alias"
            alias.symlink_to(Path(directory), target_is_directory=True)
            self.assertIsNone(selector.saved_browser_preference(alias / "target-app.txt"))

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
