#!/usr/bin/env python3
"""Secret-free contract tests for staged Developer ID signing."""
import importlib.util
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("sign_developer_id", ROOT / "scripts/sign_developer_id.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from package_application_helpers import HELPER_NAMES

TEAM = "ABCDE12345"
IDENTITY = "Developer ID Application: Test Publisher (" + TEAM + ")"


class SigningTests(unittest.TestCase):
  def setUp(self):
    self.directory = tempfile.TemporaryDirectory()
    self.addCleanup(self.directory.cleanup)
    self.app = Path(self.directory.name) / "PDFMagicOpener.app"
    self.binary("Contents/MacOS/PDFMagicOpener")
    self.plist("Contents/Info.plist", {
      "CFBundleIdentifier": module.BUNDLE_ID,
      "CFBundleExecutable": "PDFMagicOpener",
      "CFBundlePackageType": "APPL",
      "LSUIElement": False,
    })
    for name in HELPER_NAMES:
      self.binary("Contents/Helpers/" + name)
    self.binary(str(module.EXTENSION / "Contents/MacOS/PDFMagicOpenerSafari"))
    self.plist(str(module.EXTENSION / "Contents/Info.plist"), {
      "CFBundleIdentifier": module.BUNDLE_ID + ".safari",
      "CFBundleExecutable": "PDFMagicOpenerSafari",
      "CFBundlePackageType": "XPC!",
    })

  def binary(self, relative):
    path = self.app / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xcf\xfa\xed\xfe" + b"synthetic Mach-O")
    path.chmod(0o755)
    return path

  def plist(self, relative, data):
    path = self.app / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
      plistlib.dump(data, stream)

  @staticmethod
  def valid_codesign(arguments, **kwargs):
    if "--display" in arguments:
      return subprocess.CompletedProcess(arguments, 0, "", (
        "CodeDirectory v=20500 size=100 flags=0x10000(runtime)\n"
        "Authority=Developer ID Application: Test Publisher\n"
        "Authority=Developer ID Certification Authority\n"
        "TeamIdentifier=" + TEAM + "\n"))
    return subprocess.CompletedProcess(arguments, 0, "", "")

  def test_signs_helpers_and_extension_before_host_and_verifies_all(self):
    calls = []
    def tracked(arguments, **kwargs):
      calls.append(arguments)
      return self.valid_codesign(arguments, **kwargs)
    with patch.object(module.subprocess, "run", side_effect=tracked):
      targets = module.sign(self.app, TEAM, IDENTITY)
    self.assertEqual(len(targets), len(HELPER_NAMES) + 2)
    sign_calls = [c for c in calls if "--sign" in c]
    self.assertEqual([Path(c[-1]) for c in sign_calls], targets)
    self.assertEqual(targets[-2], self.app / module.EXTENSION)
    self.assertEqual(targets[-1], self.app)
    self.assertEqual(len([c for c in calls if "--verify" in c]), len(targets))
    self.assertTrue(all(c[0] == module.CODESIGN and "--timestamp" in c
                        and "--options" in c and "runtime" in c for c in sign_calls))
    self.assertIn("--entitlements", sign_calls[-2])
    self.assertNotIn("--entitlements", sign_calls[-1])

  def test_rejects_invalid_cert_signatures_and_team(self):
    def invalid(arguments, **kwargs):
      if "--display" in arguments:
        return subprocess.CompletedProcess(arguments, 0, "", (
          "CodeDirectory flags=0x0(adhoc)\nTeamIdentifier=not set\n"))
      return self.valid_codesign(arguments, **kwargs)
    with patch.object(module.subprocess, "run", side_effect=invalid):
      with self.assertRaisesRegex(ValueError, "Missing hardened"):
        module.verify(self.app, TEAM)
    with self.assertRaisesRegex(ValueError, "identity"):
      module.sign(self.app, TEAM, "Apple Development: Not Developer ID")
    with self.assertRaisesRegex(ValueError, "Apple team ID"):
      module.verify(self.app, "BAD")

  def test_rejects_unreviewed_or_missing_code_before_signing(self):
    self.assertEqual(len(module.signing_targets(self.app)), len(HELPER_NAMES) + 2)
    extra = self.binary("Contents/Resources/unreviewed-binary")
    with self.assertRaisesRegex(ValueError, "Unreviewed executable"):
      module.signing_targets(self.app)
    extra.unlink()
    unexpected = self.app / "Contents/PlugIns/Unknown.appex"
    unexpected.mkdir()
    with self.assertRaisesRegex(ValueError, "Unreviewed extension"):
      module.signing_targets(self.app)
    unexpected.rmdir()
    (self.app / "Contents/Helpers/launch-scanned-file").unlink()
    with self.assertRaises(ValueError):
      module.signing_targets(self.app)

  def test_stops_before_host_signature_when_helper_signing_fails(self):
    calls = []
    def fail(arguments, **kwargs):
      calls.append(arguments)
      raise subprocess.CalledProcessError(1, arguments)
    with patch.object(module.subprocess, "run", side_effect=fail):
      with self.assertRaises(subprocess.CalledProcessError):
        module.sign(self.app, TEAM, IDENTITY)
    self.assertEqual(len(calls), 1)
    self.assertNotEqual(calls[0][-1], str(self.app))

  def test_signs_embedded_login_item_app_before_safari_and_host(self):
    self.binary("Contents/Library/LoginItems/Updater.app/Contents/MacOS/Updater")
    helper = self.app / "Contents/Library/LoginItems/Updater.app"
    self.plist("Contents/Library/LoginItems/Updater.app/Contents/Info.plist", {
      "CFBundleIdentifier": module.BUNDLE_ID + ".updater",
      "CFBundleExecutable": "Updater",
      "CFBundlePackageType": "APPL",
    })
    targets = module.signing_targets(self.app)
    self.assertEqual(targets[-3], helper)

  def test_ci_and_release_workflow_are_isolated(self):
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/developer-id-signing.yml").read_text(encoding="utf-8")
    self.assertIn("tests/general/developer-id-signing.py -v", ci)
    self.assertIn("workflow_dispatch:", workflow)
    self.assertNotIn("pull_request:", workflow)
    self.assertIn("CODE_SIGNING_ALLOWED=NO", workflow)
    self.assertIn("scripts/package_application_helpers.py", workflow)
    self.assertIn("scripts/sign_developer_id.py", workflow)
    self.assertIn("--verify-only", workflow)
    self.assertIn("secrets.APPLE_DEVELOPER_ID_CERTIFICATE_BASE64", workflow)
    self.assertIn("secrets.APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD", workflow)
    self.assertIn("developer-id-release", workflow)
    self.assertNotIn("gh release create", workflow)


if __name__ == "__main__":
  unittest.main()
