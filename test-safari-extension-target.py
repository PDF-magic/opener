#!/usr/bin/env python3
"""Check Safari Web Extension target structure and fail-closed packaging."""
import json
from pathlib import Path
import plistlib
import sys
import unittest

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj"
SAFARI = ROOT / "extensions" / "safari"
SHARED = ROOT / "extensions" / "webextension" / "manifest.json"
BACKGROUND = ROOT / "extensions" / "webextension" / "src" / "background.js"
ICONS = ROOT / "extensions" / "webextension" / "icons"
TOOLBAR_TITLE = "PDF Magic Opener (not active)"
POPUP_DIR = ROOT / "extensions" / "webextension" / "src"
POPUP_FILES = ("popup.html", "popup.css")
TOOLBAR_ICONS = {str(size): f"icons/icon-{size}.png" for size in (16, 32, 48, 128)}
EXTENSION_ID = "local.studio.pdfmagicopener.swiftui.safari"
TARGET_ID = "D56700000000000000000009"


def verify_built_app(app: Path) -> None:
  """Inspect the real macOS bundle without launching or installing anything."""
  assert app.is_dir(), f"Missing host app: {app}"
  extension = app / "Contents" / "PlugIns" / "PDFMagicOpenerSafari.appex"
  plist_path = extension / "Contents" / "Info.plist"
  assert plist_path.is_file(), f"Missing embedded Safari extension: {plist_path}"
  with plist_path.open("rb") as f:
    info = plistlib.load(f)
  assert info["CFBundleIdentifier"] == EXTENSION_ID
  assert info["CFBundlePackageType"] == "XPC!"
  assert info["NSExtension"]["NSExtensionPointIdentifier"] == "com.apple.Safari.web-extension"
  assert info["NSExtension"]["NSExtensionPrincipalClass"] == "PDFMagicOpenerSafari.SafariWebExtensionHandler"
  executable = extension / "Contents" / "MacOS" / "PDFMagicOpenerSafari"
  assert executable.is_file(), f"Missing compiled extension executable: {executable}"
  bundled = extension / "Contents" / "Resources" / "manifest.json"
  assert bundled.is_file(), f"Missing shared web extension manifest: {bundled}"
  assert bundled.read_bytes() == SHARED.read_bytes(), "Safari manifest diverges from shared source"
  manifest = json.loads(bundled.read_text(encoding="utf-8"))
  assert manifest["permissions"] == [] and manifest["host_permissions"] == []
  assert manifest["background"] == {"service_worker": "background.js", "type": "module"}
  worker = extension / "Contents" / "Resources" / "background.js"
  assert worker.is_file(), f"Missing bundled inert background entry: {worker}"
  assert worker.read_bytes() == BACKGROUND.read_bytes(), "Safari worker differs from shared source"
  assert manifest["action"] == {
    "default_title": TOOLBAR_TITLE,
    "default_icon": TOOLBAR_ICONS,
    "default_popup": "popup.html",
  }
  for filename in POPUP_FILES:
    bundled_asset = extension / "Contents" / "Resources" / filename
    source_asset = POPUP_DIR / filename
    assert bundled_asset.is_file(), f"Missing bundled Safari popup: {filename}"
    assert bundled_asset.read_bytes() == source_asset.read_bytes(), (
      f"Safari popup asset diverges: {filename}"
    )
  for relative in TOOLBAR_ICONS.values():
    source = ROOT / "extensions" / "webextension" / relative
    bundled_icon = extension / "Contents" / "Resources" / relative
    assert bundled_icon.is_file(), f"Missing bundled toolbar icon: {relative}"
    assert bundled_icon.read_bytes() == source.read_bytes(), f"Toolbar icon diverges: {relative}"
  for forbidden in ("content_scripts", "externally_connectable"):
    assert forbidden not in manifest
  with (app / "Contents" / "Info.plist").open("rb") as f:
    host = plistlib.load(f)
  assert "CFBundleDocumentTypes" not in host
  assert host["CFBundleIdentifier"] == "local.studio.pdfmagicopener.swiftui"


class SafariExtensionTargetTests(unittest.TestCase):
  def test_plist_identifies_modern_safari_web_extension_only(self):
    with (SAFARI / "Info.plist").open("rb") as f:
      info = plistlib.load(f)
    self.assertEqual(info["CFBundlePackageType"], "XPC!")
    self.assertEqual(info["NSExtension"], {
      "NSExtensionPointIdentifier": "com.apple.Safari.web-extension",
      "NSExtensionPrincipalClass": "$(PRODUCT_MODULE_NAME).SafariWebExtensionHandler",
    })
    with (SAFARI / "SafariExtension.entitlements").open("rb") as f:
      self.assertEqual(plistlib.load(f), {"com.apple.security.app-sandbox": True})

  def test_xcode_creates_separate_target_and_embeds_appex(self):
    project = PROJECT.read_text(encoding="utf-8")
    self.assertIn(f"{TARGET_ID} = {{", project)
    for expected in (
      'productType = "com.apple.product-type.app-extension";',
      'productReference = D56700000000000000000006;',
      'name = PDFMagicOpenerSafari;',
      'dstSubfolderSpec = 13;',
      'name = "Embed App Extensions";',
      'target = D56700000000000000000009;',
      'dependencies = (D5670000000000000000000D,);',
      'targets = (A10000000000000000000008, D56700000000000000000009,);',
      'APPLICATION_EXTENSION_API_ONLY = YES;',
      'CODE_SIGN_ENTITLEMENTS = extensions/safari/SafariExtension.entitlements;',
      'INFOPLIST_FILE = extensions/safari/Info.plist;',
      'PRODUCT_BUNDLE_IDENTIFIER = local.studio.pdfmagicopener.swiftui.safari;',
      'path = extensions/webextension/manifest.json;',
      'files = (D56700000000000000000003, D56700000000000000000014, D57500000000000000000001, D57600000000000000000001, D57600000000000000000003,);',
      'fileRef = D56700000000000000000015;',
      'path = extensions/webextension/src/background.js;',
      'fileRef = D57500000000000000000002;',
      'path = extensions/webextension/icons;',
      'path = extensions/webextension/src/popup.html;',
      'path = extensions/webextension/src/popup.css;',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, project)
    self.assertEqual(project.count('productType = "com.apple.product-type.app-extension";'), 1)
    self.assertEqual(project.count('dstSubfolderSpec = 13;'), 1)

  def test_no_native_message_or_scanner_handoff(self):
    source = (SAFARI / "SafariWebExtensionHandler.swift").read_text(encoding="utf-8")
    self.assertIn("NSExtensionRequestHandling", source)
    self.assertIn("context.completeRequest(returningItems: [], completionHandler: nil)", source)
    for forbidden in ("SFExtensionMessageKey", "nativeMessaging", "NSWorkspace",
                      "FileManager", "URLSession", "Process(", "open(", "clamscan",
                      "context.inputItems", "@AppStorage", "UserDefaults"):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)

  def test_shared_manifest_is_permission_free(self):
    manifest = json.loads(SHARED.read_text(encoding="utf-8"))
    self.assertEqual(manifest["manifest_version"], 3)
    self.assertEqual(manifest["name"], "PDF Magic Opener")
    self.assertEqual(manifest["permissions"], [])
    self.assertEqual(manifest["host_permissions"], [])
    self.assertEqual(manifest["background"], {
      "service_worker": "background.js", "type": "module"
    })
    self.assertEqual(BACKGROUND.read_text(encoding="utf-8"),
                     "// Inactive shared WebExtensions background entry point.\n"
                     "// Do not listen for messages, inspect PDFs or request native access here.\n"
                     "void 0;\n")
    self.assertEqual(manifest["action"], {
      "default_title": TOOLBAR_TITLE,
      "default_icon": TOOLBAR_ICONS,
      "default_popup": "popup.html",
    })
    for filename in POPUP_FILES:
      with self.subTest(filename=filename):
        self.assertTrue((POPUP_DIR / filename).is_file())
    for size, path in TOOLBAR_ICONS.items():
      with self.subTest(size=size):
        self.assertEqual(path, f"icons/icon-{size}.png")
        self.assertTrue((ICONS / f"icon-{size}.png").is_file())
    for forbidden in ("content_scripts", "externally_connectable",
                      "web_accessible_resources", "optional_permissions"):
      self.assertNotIn(forbidden, manifest)

  def test_ci_builds_and_inspects_embedded_extension(self):
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    self.assertIn("xcodebuild -project PDFMagicOpener.xcodeproj", ci)
    self.assertIn("python3 test-safari-extension-target.py -v", ci)
    self.assertIn("python3 test-safari-extension-target.py --verify-built-app", ci)
    self.assertIn("CODE_SIGNING_ALLOWED=NO build", ci)


if __name__ == "__main__":
  if len(sys.argv) == 3 and sys.argv[1] == "--verify-built-app":
    verify_built_app(Path(sys.argv[2]))
  else:
    unittest.main()
