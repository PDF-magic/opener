#!/usr/bin/env python3
"""Portable tests for opt-in macOS Chrome native-host registration."""

import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

SOURCE = Path(__file__).parent / "native-messaging" / "register-chrome-host.py"
spec = importlib.util.spec_from_file_location("chrome_host_registration", SOURCE)
registration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registration)
VALID_ID = "abcdefghijklmnopabcdefghijklmnop"
SECOND_ID = "ponmlkjihgfedcbaponmlkjihgfedcba"


class ChromeHostRegistrationTests(unittest.TestCase):
  def setUp(self):
    self.temporary = tempfile.TemporaryDirectory(prefix="pdfmagic-chrome-registration-")
    self.addCleanup(self.temporary.cleanup)
    self.root = Path(self.temporary.name)
    self.binary = self.root / "native-host"
    self.binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    self.binary.chmod(0o700)
    self.home = self.root / "home"
    self.home.mkdir()

  def test_chrome_schema_uses_canonical_identity_and_exact_approved_origins(self):
    manifest = registration.build_manifest(self.binary, [VALID_ID, SECOND_ID, VALID_ID])
    self.assertEqual(manifest, {
      "name": json.loads((SOURCE.parent / "host-identity.json").read_text())["name"],
      "description": "PDF Magic Opener native messaging host (transport only)",
      "path": str(self.binary),
      "type": "stdio",
      "allowed_origins": [f"chrome-extension://{VALID_ID}/", f"chrome-extension://{SECOND_ID}/"],
    })
    self.assertTrue(all(origin.startswith("chrome-extension://") and origin.endswith("/")
                        for origin in manifest["allowed_origins"]))

  def test_rejects_wildcards_unapproved_and_malformed_origins(self):
    for identifiers in ([], ["*"], ["a" * 31], ["a" * 33], ["z" * 32],
                        [VALID_ID.upper()], [f"chrome-extension://{VALID_ID}/"],
                        [VALID_ID, "*"], [VALID_ID + "/"], [None]):
      with self.subTest(identifiers=identifiers):
        with self.assertRaises(ValueError):
          registration.build_manifest(self.binary, identifiers)

  def test_rejects_missing_relative_symlink_and_nonexecutable_hosts(self):
    with self.assertRaises(ValueError):
      registration.build_manifest(Path("relative-host"), [VALID_ID])
    with self.assertRaises(ValueError):
      registration.build_manifest(self.root / "missing", [VALID_ID])
    symlink = self.root / "linked-host"
    symlink.symlink_to(self.binary)
    with self.assertRaises(ValueError):
      registration.build_manifest(symlink, [VALID_ID])
    self.binary.chmod(0o600)
    with self.assertRaises(ValueError):
      registration.build_manifest(self.binary, [VALID_ID])

  def test_registers_in_mac_chrome_location_with_private_permissions(self):
    target, created = registration.register(self.binary, [VALID_ID], self.home)
    self.assertTrue(created)
    self.assertEqual(target, self.home / registration.CHROME_DIRECTORY /
                     "org.pdfmagic.opener.json")
    self.assertEqual(json.loads(target.read_text()),
                     registration.build_manifest(self.binary, [VALID_ID]))
    self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
    self.assertEqual(list(target.parent.iterdir()), [target])
    extension = json.loads((SOURCE.parents[1] / "extensions/webextension/manifest.json").read_text())
    self.assertEqual(extension["permissions"], [])
    self.assertEqual(extension["host_permissions"], [])
    self.assertNotIn("nativeMessaging", extension.get("optional_permissions", []))

  def test_identical_reinstall_is_noop_and_conflicts_preserve_user_settings(self):
    target, _ = registration.register(self.binary, [VALID_ID], self.home)
    before = target.read_bytes()
    target2, created = registration.register(self.binary, [VALID_ID], self.home)
    self.assertFalse(created)
    self.assertEqual(target2, target)
    with self.assertRaises(FileExistsError):
      registration.register(self.binary, [SECOND_ID], self.home)
    self.assertEqual(target.read_bytes(), before)
    other = target.parent / "user.host.json"
    other.write_text("custom settings")
    with self.assertRaises(FileExistsError):
      registration.register(self.binary, [SECOND_ID], self.home)
    self.assertEqual(other.read_text(), "custom settings")

  def test_rejects_symlink_registration_and_parent_without_following_them(self):
    dest = self.home / registration.CHROME_DIRECTORY
    dest.mkdir(parents=True)
    outside = self.root / "outside"
    outside.write_text("do not touch", encoding="utf-8")
    (dest / "org.pdfmagic.opener.json").symlink_to(outside)
    with self.assertRaises(FileExistsError):
      registration.register(self.binary, [VALID_ID], self.home)
    self.assertEqual(outside.read_text(), "do not touch")
    (dest / "org.pdfmagic.opener.json").unlink()
    dest.rmdir()
    dest.symlink_to(self.root, target_is_directory=True)
    with self.assertRaises(ValueError):
      registration.register(self.binary, [VALID_ID], self.home)
    self.assertFalse((self.root / "org.pdfmagic.opener.json").exists())

  def test_no_extension_id_cannot_publish_registration(self):
    with self.assertRaises(ValueError):
      registration.register(self.binary, [], self.home)
    self.assertFalse((self.home / registration.CHROME_DIRECTORY).exists())


if __name__ == "__main__":
  unittest.main()
