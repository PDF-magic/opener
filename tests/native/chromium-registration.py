"""Portable, isolated tests for macOS Chromium-family host registration."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parent / "native-messaging" / "register-chromium-hosts.py"
SPEC = importlib.util.spec_from_file_location("chromium_host_registration", SOURCE)
registration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(registration)


class ChromiumHostRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.home = root / "home"
        self.home.mkdir()
        self.binary = root / "host"
        self.binary.write_bytes(b"#!/bin/sh\nexit 0\n")
        self.binary.chmod(0o700)
        self.manifest = self.home / "Library/Application Support/Google/Chrome/NativeMessagingHosts/org.pdfmagic.opener.json"
        self.manifest.parent.mkdir(parents=True)
        self.data = {
            "name": registration.HOST_NAME,
            "description": "PDF Magic Opener native transport",
            "path": str(self.binary),
            "type": "stdio",
            "allowed_origins": ["chrome-extension://" + "a" * 32 + "/"],
        }
        self.save_manifest()

    def save_manifest(self):
        self.manifest.write_text(json.dumps(self.data), encoding="utf-8")

    def test_registers_all_eight_supported_browsers_using_correct_user_locations(self):
        paths = registration.register_chromium_hosts(self.home)
        self.assertEqual(set(paths), {"chrome", "chromium", "chrome-for-testing", "brave", "edge", "vivaldi", "opera", "arc"})
        self.assertEqual(paths["opera"], paths["chrome"])
        self.assertEqual(len(set(paths.values())), 7)
        for browser, relative in registration.BROWSER_LOCATIONS.items():
            expected = self.home / "Library/Application Support" / relative / "NativeMessagingHosts" / "org.pdfmagic.opener.json"
            self.assertEqual(paths[browser], expected)
            self.assertEqual(expected.read_bytes(), self.manifest.read_bytes())
        self.assertFalse((self.home / "Library/Application Support/Mozilla").exists())

    def test_second_registration_preserves_existing_files(self):
        paths = registration.register_chromium_hosts(self.home)
        original = {p: p.stat().st_mtime_ns for p in set(paths.values())}
        registration.register_chromium_hosts(self.home)
        self.assertEqual(original, {p: p.stat().st_mtime_ns for p in set(paths.values())})

    def test_collision_fails_before_any_new_location_is_created(self):
        paths = registration.register_chromium_hosts(self.home)
        chromium = paths["chromium"]
        chromium.write_text('{"user":"customized"}', encoding="utf-8")
        brave = paths["brave"]
        brave.unlink()
        with self.assertRaisesRegex(registration.RegistrationError, "differs"):
            registration.register_chromium_hosts(self.home)
        self.assertFalse(brave.exists())
        self.assertEqual(chromium.read_text(), '{"user":"customized"}')

    def test_rejects_unapproved_or_malformed_origins_and_executables(self):
        invalid = [[], ["chrome-extension://*/"], ["https://example.com/"],
                   ["chrome-extension://" + "A" * 32 + "/"],
                   ["chrome-extension://" + "a" * 32 + "/"] * 2]
        for origins in invalid:
            with self.subTest(origins=origins):
                self.data["allowed_origins"] = origins
                self.save_manifest()
                with self.assertRaises(registration.RegistrationError):
                    registration.register_chromium_hosts(self.home)
        self.data["allowed_origins"] = ["chrome-extension://" + "a" * 32 + "/"]
        self.data["path"] = "./relative-host"
        self.save_manifest()
        with self.assertRaises(registration.RegistrationError):
            registration.register_chromium_hosts(self.home)
        self.assertFalse((self.home / "Library/Application Support/Chromium").exists())

    def test_symlinked_directory_is_never_followed(self):
        other = Path(self.temp.name) / "other"
        other.mkdir()
        (self.home / "Library/Application Support/Chromium").symlink_to(other, target_is_directory=True)
        with self.assertRaises(registration.RegistrationError):
            registration.register_chromium_hosts(self.home)
        self.assertEqual(list(other.iterdir()), [])

    def test_requires_existing_approved_chrome_registration(self):
        self.manifest.unlink()
        with self.assertRaises(registration.RegistrationError):
            registration.register_chromium_hosts(self.home)
        self.assertFalse((self.home / "Library/Application Support/Chromium").exists())

    def test_rejects_existing_symlink_manifest(self):
        expected = self.home / "Library/Application Support/BraveSoftware/Brave-Browser/NativeMessagingHosts"
        expected.mkdir(parents=True)
        (expected / "org.pdfmagic.opener.json").symlink_to(self.manifest)
        with self.assertRaises(registration.RegistrationError):
            registration.register_chromium_hosts(self.home)
        self.assertFalse((self.home / "Library/Application Support/Chromium").exists())


if __name__ == "__main__":
    unittest.main()
