#!/usr/bin/env python3
"""Portable tests for opt-in macOS Chrome native-host registration."""

import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "native-messaging" / "register-chrome-host.py"
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

  def test_rejects_traversal_control_characters_and_symlinked_host_ancestors(self):
    parent = self.root / "real-host-folder"
    parent.mkdir()
    executable = parent / "host"
    executable.write_bytes(self.binary.read_bytes())
    executable.chmod(0o700)
    alias = self.root / "alias-host-folder"
    alias.symlink_to(parent, target_is_directory=True)
    for path in (alias / "host", self.root / ".." / "host",
                 self.root / "host\ninjection", self.root / "bad\x00host"):
      with self.subTest(path=str(path)):
        with self.assertRaises(ValueError):
          registration.build_manifest(path, [VALID_ID])
    self.assertEqual(registration.build_manifest(executable, [VALID_ID])["path"],
                     str(executable))

  def test_rejects_symlinked_home_before_creating_registration(self):
    linked = self.root / "linked-home"
    linked.symlink_to(self.home, target_is_directory=True)
    with self.assertRaises(ValueError):
      registration.register(self.binary, [VALID_ID], linked)
    self.assertEqual(list(self.home.iterdir()), [])

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


  def test_registration_survives_atomic_application_update_at_same_executable_path(self):
    """Updating executable bytes at a stable path must preserve the manifest and user files."""
    import os
    import subprocess

    target, created = registration.register(self.binary, [VALID_ID], self.home)
    self.assertTrue(created)
    original_manifest = target.read_bytes()
    original_inode = target.stat().st_ino
    user_file = target.parent / "user-managed-config.txt"
    user_file.write_text("preserve this setting", encoding="utf-8")

    staged = self.root / "native-host-version-2"
    staged.write_text("#!/bin/sh\nprintf 'updated-version\\n'\n", encoding="utf-8")
    staged.chmod(0o700)
    os.replace(staged, self.binary)
    self.assertEqual(subprocess.check_output([str(self.binary)], text=True).strip(),
                     "updated-version", "the registered path must execute the updated version")

    target_after, created_again = registration.register(self.binary, [VALID_ID], self.home)
    self.assertFalse(created_again, "same-path application update is already registered")
    self.assertEqual(target_after, target)
    self.assertEqual(target.read_bytes(), original_manifest)
    self.assertEqual(target.stat().st_ino, original_inode, "registration is not silently rewritten")
    self.assertEqual(json.loads(target.read_text())["path"], str(self.binary))
    self.assertEqual(user_file.read_text(), "preserve this setting")
    self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)

  def test_relocated_update_fails_closed_without_overwriting_saved_registration(self):
    """An app move requires reviewed migration, not silent origin or path replacement."""
    updated = self.root / "UpdatedApplication.app" / "Contents" / "MacOS" / "native-host"
    updated.parent.mkdir(parents=True)
    updated.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    updated.chmod(0o700)
    target, _ = registration.register(self.binary, [VALID_ID], self.home)
    original_manifest = target.read_bytes()
    other = target.parent / "user.host.json"
    other.write_text('{"customized":true}\n', encoding="utf-8")

    self.binary.unlink()
    with self.assertRaises(ValueError):
      registration.build_manifest(self.binary, [VALID_ID])
    with self.assertRaises(FileExistsError):
      registration.register(updated, [VALID_ID], self.home)
    with self.assertRaises(FileExistsError):
      registration.register(updated, [SECOND_ID], self.home)

    self.assertEqual(target.read_bytes(), original_manifest)
    self.assertEqual(json.loads(target.read_text())["path"], str(self.binary))
    self.assertEqual(other.read_text(encoding="utf-8"), '{"customized":true}\n')
    self.assertTrue(updated.is_file())
    self.assertFalse(self.binary.exists(), "obsolete registration is not treated as working")


if __name__ == "__main__":
  unittest.main()
