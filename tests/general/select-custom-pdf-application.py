#!/usr/bin/env python3
"""Test manual PDF application preference safety without using user settings."""
import importlib.util
from pathlib import Path
import os
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "select_custom_pdf_application", ROOT / "select-custom-pdf-application.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class CustomPDFSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="opener-custom-app-")
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.setting = self.folder / "target-app.txt"
        self.setting.write_text("com.brave.Browser\n")

    def subprocess_result(self, *, selected=b"org.example.customBrowser\n", picker_exit=0,
                          verifier_exit=0):
        def invoke(args, **kwargs):
            self.assertTrue(kwargs.get("capture_output"))
            if args[0] == str(app.NATIVE_PICKER):
                return subprocess.CompletedProcess(args, picker_exit, selected, b"")
            if args[0] == str(app.PDF_VERIFIER):
                self.assertEqual(args[1], "org.example.customBrowser")
                return subprocess.CompletedProcess(args, verifier_exit, b"", b"")
            raise AssertionError("Unexpected helper")
        return invoke

    def test_explicit_bundle_is_verified_twice_and_saved_atomically(self):
        with patch.object(app.subprocess, "run", side_effect=self.subprocess_result()) as run:
            selected = app.choose_and_save("/Volumes/Browser Apps/My Browser.app",
                                           self.setting)
        self.assertEqual(selected, "org.example.customBrowser")
        self.assertEqual(self.setting.read_text(), selected + "\n")
        self.assertEqual(stat.S_IMODE(self.setting.stat().st_mode), 0o600)
        self.assertEqual(list(self.folder.iterdir()), [self.setting])
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0], [
            str(app.NATIVE_PICKER), "--application",
            "/Volumes/Browser Apps/My Browser.app"
        ])

    def test_interactive_picker_without_path_still_verifies(self):
        with patch.object(app.subprocess, "run", side_effect=self.subprocess_result()) as run:
            self.assertEqual(app.choose_and_save(destination=self.setting),
                             "org.example.customBrowser")
        self.assertEqual(run.call_args_list[0].args[0], [str(app.NATIVE_PICKER)])
        self.assertIsNone(run.call_args_list[0].kwargs["timeout"])

    def test_cancel_failure_or_bad_identity_leaves_existing_choice_unchanged(self):
        cases = [
            {"picker_exit": 1},
            {"selected": b""},
            {"selected": b"com..bad\n"},
            {"selected": b"local.studio.brave-pdf-opener\n"},
            {"selected": b"org.example.customBrowser\nextra\n"},
            {"selected": b"\xff\n"},
            {"verifier_exit": 1},
        ]
        for options in cases:
            with self.subTest(options=options):
                self.setting.write_text("com.apple.Safari\n")
                with patch.object(app.subprocess, "run", self.subprocess_result(**options)):
                    with self.assertRaises(RuntimeError):
                        app.choose_and_save("/Applications/Browser.app", self.setting)
                self.assertEqual(self.setting.read_text(), "com.apple.Safari\n")

    def test_invalid_paths_never_invoke_native_picker(self):
        for path in ("relative.app", "/Applications/Other.txt", "../bad.app"):
            with self.subTest(path=path):
                with patch.object(app.subprocess, "run", side_effect=AssertionError):
                    with self.assertRaises(ValueError):
                        app.choose_and_save(path, self.setting)
                self.assertEqual(self.setting.read_text(), "com.brave.Browser\n")

    def test_does_not_follow_existing_symlink_or_replace_a_directory(self):
        original = self.folder / "original.txt"
        original.write_text("keep me")
        self.setting.unlink()
        self.setting.symlink_to(original)
        with patch.object(app.subprocess, "run", self.subprocess_result()):
            with self.assertRaises(RuntimeError):
                app.choose_and_save("/Applications/Browser.app", self.setting)
        self.assertEqual(original.read_text(), "keep me")
        self.assertTrue(self.setting.is_symlink())
        self.setting.unlink()
        self.setting.mkdir()
        with self.assertRaises(RuntimeError):
            app.persist_preference("org.example.customBrowser", self.setting)
        self.assertTrue(self.setting.is_dir())

    def test_missing_setting_can_be_created_but_not_in_missing_directory(self):
        self.setting.unlink()
        app.persist_preference("org.example.customBrowser", self.setting)
        self.assertEqual(self.setting.read_text(), "org.example.customBrowser\n")
        with self.assertRaises(OSError):
            app.persist_preference("org.example.customBrowser",
                                   self.folder / "missing" / "target-app.txt")

    def test_directory_symlink_must_not_be_used(self):
        shortcut = self.folder / "shortcut"
        shortcut.symlink_to(self.folder, target_is_directory=True)
        with self.assertRaises(OSError):
            app.persist_preference("org.example.customBrowser", shortcut / "target-app.txt")
        self.assertEqual(self.setting.read_text(), "com.brave.Browser\n")

    def test_invalid_bundle_id_never_writes(self):
        for identifier in ("", "bad", "org..bad", "org.example.BAD\nother",
                           "local.studio.brave-pdf-opener"):
            with self.subTest(identifier=identifier):
                with self.assertRaises(ValueError):
                    app.persist_preference(identifier, self.setting)
                self.assertEqual(self.setting.read_text(), "com.brave.Browser\n")


if __name__ == "__main__":
    unittest.main()
