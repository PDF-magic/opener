#!/usr/bin/env python3
"""Regression coverage for fail-closed persisted application validation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import file_launcher as launcher


class ConfigurationValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.primary = self.root / "target-app.txt"
        self.fallback = self.root / "fallback-app.txt"
        for key, path in (("TARGET_APP_CONFIG", self.primary), ("FALLBACK_APP_CONFIG", self.fallback)):
            mock = patch.object(launcher, key, path)
            mock.start()
            self.addCleanup(mock.stop)

    def test_missing_settings_preserve_existing_defaults(self):
        self.assertEqual(launcher.pdf_target_application(), "com.brave.Browser")
        self.assertIsNone(launcher.pdf_fallback_application())

    def test_valid_choices_are_preserved(self):
        self.primary.write_bytes(b"com.apple.Preview\n")
        self.fallback.write_bytes(b"org.mozilla.firefox\n")
        self.assertEqual(launcher.pdf_target_application(), "com.apple.Preview")
        self.assertEqual(launcher.pdf_fallback_application("com.apple.Preview"), "org.mozilla.firefox")
        self.assertEqual(self.primary.read_bytes(), b"com.apple.Preview\n")

    def test_matching_fallback_is_not_used(self):
        self.fallback.write_bytes(b"com.apple.Preview\n")
        self.assertIsNone(launcher.pdf_fallback_application("com.apple.Preview"))

    def test_invalid_primary_and_fallback_fail_closed(self):
        invalid = [
            b"", b"com.apple.Preview\ncom.brave.Browser",
            b" com.apple.Preview", b"com.apple.Preview ", b"com.apple.Preview\r\n",
            b"com.apple.Preview\x00", b"com..apple", b"not-a-bundle",
            b"local.studio.brave-pdf-opener", b"\xff", b"a" * 257,
        ]
        for raw in invalid:
            for path, reader in ((self.primary, launcher.pdf_target_application),
                                 (self.fallback, launcher.pdf_fallback_application)):
                with self.subTest(raw=raw, path=path.name):
                    path.write_bytes(raw)
                    with self.assertRaises(RuntimeError):
                        reader()
                    self.assertEqual(path.read_bytes(), raw)
                    path.unlink()

    def test_nonregular_files_and_symlinks_are_rejected(self):
        outside = self.root / "outside"
        outside.write_text("com.apple.Preview")
        for path, reader in ((self.primary, launcher.pdf_target_application),
                             (self.fallback, launcher.pdf_fallback_application)):
            path.symlink_to(outside)
            with self.assertRaises(RuntimeError):
                reader()
            path.unlink()
            path.mkdir()
            with self.assertRaises(RuntimeError):
                reader()
            path.rmdir()

    def test_system_default_token_only_allowed_for_primary(self):
        self.primary.write_text("system-default-browser\n")
        with patch.object(launcher, "_resolve_default_browser", return_value="com.apple.Safari") as resolver:
            self.assertEqual(launcher.pdf_target_application(), "com.apple.Safari")
            resolver.assert_called_once()
        self.fallback.write_text("system-default-browser\n")
        with self.assertRaises(RuntimeError):
            launcher.pdf_fallback_application()


if __name__ == "__main__":
    unittest.main()
