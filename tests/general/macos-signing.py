#!/usr/bin/env python3
"""Prevent macOS release-signing privilege drift (opener-1138)."""
import importlib.util
from pathlib import Path
import plistlib
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj"
HOST_ENTITLEMENTS = ROOT / "PDFMagicOpenerApp/PDFMagicOpener.entitlements"
SAFARI_ENTITLEMENTS = ROOT / "extensions/safari/SafariExtension.entitlements"
VERIFIER = ROOT / "scripts/verify_macos_app_signature.py"
spec = importlib.util.spec_from_file_location("verify_macos_app_signature", VERIFIER)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def configuration(project, config_id):
  match = re.search(
    r"(?ms)^    " + config_id + r" = \{\n"
    r"      isa = XCBuildConfiguration;\n"
    r"      buildSettings = \{\n(?P<settings>.*?)"
    r"^      \};\n      name = (?P<name>Debug|Release);",
    project,
  )
  if not match:
    raise AssertionError("Missing Xcode configuration " + config_id)
  return match.group("name"), match.group("settings")


class MacOSSigningTests(unittest.TestCase):
  def test_entitlements_are_exact_and_do_not_grant_unreviewed_privileges(self):
    with HOST_ENTITLEMENTS.open("rb") as handle:
      self.assertEqual(plistlib.load(handle), {})
    with SAFARI_ENTITLEMENTS.open("rb") as handle:
      self.assertEqual(plistlib.load(handle), {"com.apple.security.app-sandbox": True})
    self.assertEqual(verifier.EXPECTED[0][3], {})
    self.assertEqual(verifier.EXPECTED[1][3], {"com.apple.security.app-sandbox": True})

  def test_xcode_uses_explicit_host_rights_and_release_hardened_runtime(self):
    project = PROJECT.read_text(encoding="utf-8")
    host = "CODE_SIGN_ENTITLEMENTS = PDFMagicOpenerApp/PDFMagicOpener.entitlements;"
    safari = "CODE_SIGN_ENTITLEMENTS = extensions/safari/SafariExtension.entitlements;"
    for config_id, name, expected_entitlements in (
      ("A1000000000000000000000E", "Debug", host),
      ("A1000000000000000000000F", "Release", host),
      ("D56700000000000000000011", "Debug", safari),
      ("D56700000000000000000012", "Release", safari),
    ):
      with self.subTest(config=name, target=config_id):
        found_name, settings = configuration(project, config_id)
        self.assertEqual(found_name, name)
        self.assertIn(expected_entitlements, settings)
        self.assertEqual(settings.count("CODE_SIGN_ENTITLEMENTS ="), 1)
        if name == "Release":
          self.assertIn("ENABLE_HARDENED_RUNTIME = YES;", settings)
          self.assertIn("CODE_SIGN_INJECT_BASE_ENTITLEMENTS = NO;", settings)
    self.assertEqual(project.count("ENABLE_HARDENED_RUNTIME = YES;"), 2)
    self.assertEqual(project.count("CODE_SIGN_INJECT_BASE_ENTITLEMENTS = NO;"), 2)

  def test_codesign_verifier_rejects_missing_runtime_and_extra_entitlements(self):
    verifier.verify_runtime_flags("CodeDirectory flags=0x10000(runtime)")
    verifier.verify_runtime_flags("CodeDirectory flags=0x12000(runtime,library-validation)")
    for details in ("flags=0x0(none)", "flags=0x2(adhoc)", "not signed"):
      with self.subTest(details=details), self.assertRaises(ValueError):
        verifier.verify_runtime_flags(details)
    with self.assertRaises(ValueError):
      verifier.verify_entitlements(
        {"com.apple.security.cs.disable-library-validation": True}, {})
    with self.assertRaises(ValueError):
      verifier.verify_entitlements(
        {"com.apple.security.app-sandbox": True,
         "com.apple.security.network.client": True},
        {"com.apple.security.app-sandbox": True})

  def test_distribution_ci_validates_source_and_signed_release_bundles(self):
    workflow = (ROOT / ".github/workflows/distribution-readiness.yml").read_text(
      encoding="utf-8")
    self.assertIn("python3 tests/general/macos-signing.py -v", workflow)
    self.assertIn("runs-on: macos-latest", workflow)
    self.assertIn("-configuration Release", workflow)
    self.assertIn("CODE_SIGN_IDENTITY=-", workflow)
    self.assertIn("scripts/verify_macos_app_signature.py --app", workflow)
    self.assertNotIn("APPLE_ID", workflow)
    self.assertNotIn("DEVELOPER_ID", workflow)


if __name__ == "__main__":
  unittest.main()
