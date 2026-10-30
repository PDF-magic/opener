#!/usr/bin/env python3
"""Test Safari Web Extension least-privilege permission handling and packaging."""
import copy
import json
from pathlib import Path
import plistlib
import sys
import unittest

ROOT = Path(__file__).resolve().parent
SAFARI = ROOT / "extensions" / "safari"
SOURCE_MANIFEST = ROOT / "extensions" / "webextension" / "manifest.json"
ENTITLEMENTS = SAFARI / "SafariExtension.entitlements"
HANDLER = SAFARI / "SafariWebExtensionHandler.swift"


def validate_safari_permissions(manifest, entitlements):
  """Reject unexpected privileges; this is not a Safari runtime grant check."""
  assert manifest["manifest_version"] == 3
  assert manifest["incognito"] == "not_allowed"
  assert manifest["permissions"] == [], "No installation-time browser API grants"
  assert manifest["host_permissions"] == [], "No installation-time website grants"
  assert manifest["optional_permissions"] == ["downloads"], "Only optional download consent"
  for forbidden in (
    "optional_host_permissions", "content_scripts", "externally_connectable",
    "web_accessible_resources", "content_security_policy",
  ):
    assert forbidden not in manifest, f"Unexpected Safari manifest capability: {forbidden}"
  assert entitlements == {"com.apple.security.app-sandbox": True}, (
    "Safari native extension must remain sandbox-only"
  )


def verify_built_app(app):
  """Inspect the packaged .appex, without installing or activating Safari."""
  extension = app / "Contents" / "PlugIns" / "PDFMagicOpenerSafari.appex"
  with (extension / "Contents" / "Info.plist").open("rb") as file:
    info = plistlib.load(file)
  assert info["CFBundleIdentifier"] == "local.studio.pdfmagicopener.swiftui.safari"
  assert info["NSExtension"]["NSExtensionPointIdentifier"] == "com.apple.Safari.web-extension"
  bundled = extension / "Contents" / "Resources" / "manifest.json"
  assert bundled.read_bytes() == SOURCE_MANIFEST.read_bytes(), (
    "Packaged Safari permission policy differs from reviewed shared manifest"
  )
  with ENTITLEMENTS.open("rb") as file:
    entitlements = plistlib.load(file)
  validate_safari_permissions(json.loads(bundled.read_text(encoding="utf-8")), entitlements)


class SafariPermissionTests(unittest.TestCase):
  @classmethod
  def setUpClass(cls):
    cls.manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    with ENTITLEMENTS.open("rb") as file:
      cls.entitlements = plistlib.load(file)

  def test_safari_extension_requires_no_install_time_permissions(self):
    validate_safari_permissions(self.manifest, self.entitlements)
    with (SAFARI / "Info.plist").open("rb") as file:
      info = plistlib.load(file)
    self.assertEqual(info["NSExtension"]["NSExtensionPointIdentifier"],
                     "com.apple.Safari.web-extension")

  def test_extra_browser_permissions_and_website_grants_are_rejected(self):
    changes = (
      ("permissions", ["tabs"]),
      ("permissions", ["nativeMessaging"]),
      ("host_permissions", ["<all_urls>"]),
      ("optional_permissions", ["downloads", "nativeMessaging"]),
      ("optional_permissions", []),
      ("incognito", "spanning"),
    )
    for key, value in changes:
      with self.subTest(key=key, value=value):
        altered = copy.deepcopy(self.manifest)
        altered[key] = value
        with self.assertRaises(AssertionError):
          validate_safari_permissions(altered, self.entitlements)
    for key in ("optional_host_permissions", "content_scripts", "externally_connectable"):
      with self.subTest(key=key):
        altered = copy.deepcopy(self.manifest)
        altered[key] = ["https://example.org/*"]
        with self.assertRaises(AssertionError):
          validate_safari_permissions(altered, self.entitlements)

  def test_native_entitlement_escalation_is_rejected(self):
    for bad in (
      {},
      {"com.apple.security.app-sandbox": False},
      {"com.apple.security.app-sandbox": True,
       "com.apple.security.network.client": True},
      {"com.apple.security.app-sandbox": True,
       "com.apple.security.application-groups": ["group.example"]},
    ):
      with self.subTest(bad=bad), self.assertRaises(AssertionError):
        validate_safari_permissions(self.manifest, bad)

  def test_native_request_handler_cannot_grant_permission_or_open_pdf(self):
    source = HANDLER.read_text(encoding="utf-8")
    self.assertIn("context.completeRequest(returningItems: [], completionHandler: nil)",
                  source)
    for forbidden in (
      "SFExtensionMessageKey", "sendNativeMessage(", "connectNative(",
      "NSWorkspace", "URLSession", "Process(", "FileManager", "clamscan",
      "context.inputItems", "UserDefaults", "@AppStorage",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)

  def test_xcode_extension_keeps_explicit_sandbox_entitlements(self):
    project = (ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj").read_text(
      encoding="utf-8"
    )
    self.assertIn(
      "CODE_SIGN_ENTITLEMENTS = extensions/safari/SafariExtension.entitlements;",
      project
    )
    self.assertIn("APPLICATION_EXTENSION_API_ONLY = YES;", project)


if __name__ == "__main__":
  if len(sys.argv) == 3 and sys.argv[1] == "--verify-built-app":
    verify_built_app(Path(sys.argv[2]))
  else:
    unittest.main()
