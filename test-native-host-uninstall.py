#!/usr/bin/env python3
"""Disposable tests for uninstalling only matching native messaging registrations."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "native-messaging/unregister-hosts.py"
spec = importlib.util.spec_from_file_location("unregister_native_hosts", SOURCE)
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)

CHROME_ID = "abcdefghijklmnopabcdefghijklmnop"
OTHER_ID = "ponmlkjihgfedcbaponmlkjihgfedcba"


class NativeHostUninstallTests(unittest.TestCase):
  def setUp(self):
    temp = tempfile.TemporaryDirectory(prefix="pdfmagic-native-uninstall-")
    self.addCleanup(temp.cleanup)
    self.root = Path(temp.name)
    self.home = self.root / "home"
    self.home.mkdir()
    self.host = self.root / "native-host"
    self.host.write_text("#!/bin/sh\nexit 0\n")
    self.host.chmod(0o700)

  def manifest(self, browser, platform="darwin", host=None, ids=(CHROME_ID,)):
    host = self.host if host is None else host
    definition = cleanup._expected_manifest(browser, host, ids, browser == "firefox")
    directory = (cleanup.CHROME_DIRECTORY if browser == "chrome" else
                 cleanup.FIREFOX_MAC_DIRECTORY if platform == "darwin" else
                 cleanup.FIREFOX_LINUX_DIRECTORY)
    target = self.home / directory / cleanup.MANIFEST_NAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target

  def remove(self, *browsers, platform="darwin", host=None, ids=(CHROME_ID,), development=True):
    return cleanup.unregister(self.host if host is None else host,
                              browsers=browsers, home=self.home, platform=platform,
                              extension_ids=ids if "chrome" in browsers else (),
                              development=development if "firefox" in browsers else False)

  def test_removes_exact_chrome_and_firefox_registrations_without_other_files(self):
    chrome = self.manifest("chrome")
    firefox = self.manifest("firefox")
    other = chrome.parent / "user.custom.host.json"
    other.write_text("user settings")
    self.assertEqual(self.remove("chrome", "firefox"), [chrome, firefox])
    self.assertFalse(chrome.exists())
    self.assertFalse(firefox.exists())
    self.assertEqual(other.read_text(), "user settings")
    self.assertTrue(self.host.exists())
    self.assertEqual(self.remove("chrome", "firefox"), [])

  def test_linux_firefox_development_uninstall_after_executable_removed(self):
    target = self.manifest("firefox", platform="linux")
    self.host.unlink()
    self.assertEqual(self.remove("firefox", platform="linux"), [target])
    self.assertFalse(target.exists())

  def test_absent_registrations_do_not_create_directories(self):
    self.assertEqual(self.remove("chrome", "firefox"), [])
    self.assertEqual(list(self.home.iterdir()), [])

  def test_wrong_host_path_or_exact_origin_preserves_user_registration(self):
    target = self.manifest("chrome", ids=(CHROME_ID, OTHER_ID))
    original = target.read_bytes()
    with self.assertRaisesRegex(ValueError, "modified"):
      self.remove("chrome", ids=(OTHER_ID, CHROME_ID))
    with self.assertRaisesRegex(ValueError, "modified"):
      self.remove("chrome", host=self.root / "relocated", ids=(CHROME_ID, OTHER_ID))
    self.assertEqual(target.read_bytes(), original)
    self.assertEqual(self.remove("chrome", ids=(CHROME_ID, OTHER_ID)), [target])

  def test_customized_and_invalid_manifests_are_preserved(self):
    for change in (
      {"allowed_origins": ["chrome-extension://different/"]},
      {"path": "/tmp/another-host"},
      {"extra": True},
      {"type": "not-stdio"},
    ):
      with self.subTest(change=change):
        target = self.manifest("chrome")
        content = json.loads(target.read_text())
        content.update(change)
        target.write_text(json.dumps(content, indent=2) + "\n")
        before = target.read_bytes()
        with self.assertRaisesRegex(ValueError, "modified"):
          self.remove("chrome")
        self.assertEqual(target.read_bytes(), before)
    target.write_text("not-json")
    with self.assertRaises(ValueError):
      self.remove("chrome")
    self.assertEqual(target.read_text(), "not-json")

  def test_refuses_symlinked_manifest_and_parent_without_touching_outside(self):
    target = self.manifest("chrome")
    outside = self.root / "outside.json"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(outside)
    with self.assertRaises(ValueError):
      self.remove("chrome")
    self.assertEqual(outside.read_bytes(), cleanup._expected_bytes_for_test if False else
                     (json.dumps(cleanup._expected_manifest("chrome", self.host, (CHROME_ID,), False),
                                 indent=2) + "\n").encode())
    target.unlink()
    target.parent.rmdir()
    outside_directory = self.root / "redirect"
    outside_directory.mkdir()
    (outside_directory / cleanup.MANIFEST_NAME).write_text("untouched")
    target.parent.symlink_to(outside_directory, target_is_directory=True)
    with self.assertRaises(ValueError):
      self.remove("chrome")
    self.assertEqual((outside_directory / cleanup.MANIFEST_NAME).read_text(), "untouched")

  def test_does_not_delete_other_browser_if_one_registration_is_modified(self):
    chrome = self.manifest("chrome")
    firefox = self.manifest("firefox")
    firefox.write_text("customized")
    with self.assertRaises(ValueError):
      self.remove("chrome", "firefox")
    self.assertTrue(chrome.exists())
    self.assertEqual(firefox.read_text(), "customized")

  def test_rejects_unsupported_platforms_and_unreviewed_identity(self):
    for options in (
      dict(browsers=["chrome"], platform="linux", extension_ids=[CHROME_ID]),
      dict(browsers=["firefox"], platform="win32", development=True),
      dict(browsers=["firefox"], platform="linux", development=False),
      dict(browsers=["chrome"], platform="darwin", extension_ids=["*"]),
      dict(browsers=["chrome"], platform="darwin", extension_ids=[]),
      dict(browsers=["chrome", "chrome"], platform="darwin", extension_ids=[CHROME_ID]),
      dict(browsers=["firefox"], platform="linux", extension_ids=[CHROME_ID], development=True),
    ):
      with self.subTest(options=options):
        with self.assertRaises(ValueError):
          cleanup.unregister(self.host, home=self.home, **options)

  def test_no_scanner_or_permission_changes_and_real_linux_cli(self):
    target = self.manifest("firefox", platform="linux")
    extension = json.loads((ROOT / "extensions/webextension/manifest.json").read_text())
    self.assertNotIn("nativeMessaging", extension.get("permissions", []))
    self.assertNotIn("nativeMessaging", extension.get("optional_permissions", []))
    before = self.host.read_bytes()
    # CLI uses real platform detection on Linux; macOS uses the same API tests.
    if sys.platform == "linux":
      done = subprocess.run([sys.executable, str(SOURCE), "--browser", "firefox",
                             "--host-path", str(self.host), "--development"],
                            env={**os.environ, "HOME": str(self.home)},
                            capture_output=True, text=True, check=False)
      self.assertEqual(done.returncode, 0, done.stderr)
      self.assertFalse(target.exists())
    self.assertEqual(self.host.read_bytes(), before)


if __name__ == "__main__":
  unittest.main()
