#!/usr/bin/env python3
"""Portable regression checks for opt-in Safari activation test coverage."""
import plistlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SAFARI = ROOT / "extensions" / "safari"
PROBE = ROOT / "test-safari-extension-activation.swift"
CI = ROOT / ".github" / "workflows" / "ci.yml"


class SafariExtensionActivationTests(unittest.TestCase):
  def test_probe_uses_read_only_safari_services_state(self):
    source = PROBE.read_text(encoding="utf-8")
    self.assertIn("import SafariServices", source)
    self.assertIn("SFSafariExtensionManager.getStateOfSafariExtension(", source)
    self.assertIn("withIdentifier: safariExtensionIdentifier", source)
    self.assertIn("state.isEnabled", source)
    self.assertIn('arguments[0] == "--expect"', source)
    self.assertIn('arguments == ["--self-test"]', source)
    self.assertIn("guard let state else", source)
    self.assertIn("exit(2)", source)
    for forbidden in (
      "showPreferencesForExtension", "openSafariExtensionPreferences",
      "setEnabled", "UserDefaults", "AppleScript", "NSAppleScript",
      "NSWorkspace", "Process(", "nativeMessaging", "clamscan",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, source)

  def test_probe_matches_the_embedded_safari_extension_id(self):
    source = PROBE.read_text(encoding="utf-8")
    project = (ROOT / "PDFMagicOpener.xcodeproj" / "project.pbxproj").read_text(
      encoding="utf-8"
    )
    extension_id = "local.studio.pdfmagicopener.swiftui.safari"
    self.assertIn(f'private let safariExtensionIdentifier = "{extension_id}"', source)
    self.assertIn(f"PRODUCT_BUNDLE_IDENTIFIER = {extension_id};", project)
    with (SAFARI / "Info.plist").open("rb") as f:
      info = plistlib.load(f)
    self.assertEqual(info["CFBundleIdentifier"], "$(PRODUCT_BUNDLE_IDENTIFIER)")
    self.assertEqual(
      info["NSExtension"]["NSExtensionPointIdentifier"],
      "com.apple.Safari.web-extension"
    )

  def test_activation_never_counts_missing_or_wrong_state_as_success(self):
    source = PROBE.read_text(encoding="utf-8")
    self.assertIn("guard let observed else { return false }", source)
    for expected in (
      "precondition(matches(.enabled, observed: true))",
      "precondition(matches(.disabled, observed: false))",
      "precondition(!matches(.enabled, observed: false))",
      "precondition(!matches(.disabled, observed: true))",
      "precondition(!matches(.enabled, observed: nil))",
      "precondition(!matches(.disabled, observed: nil))",
    ):
      self.assertIn(expected, source)

  def test_ci_compiles_and_self_tests_the_probe_without_enabling_safari(self):
    ci = CI.read_text(encoding="utf-8")
    self.assertIn("python3 tests/general/safari-extension-activation.py -v", ci)
    self.assertIn(
      "swiftc -parse-as-library -warnings-as-errors test-safari-extension-activation.swift",
      ci
    )
    self.assertIn('"$RUNNER_TEMP/TestSafariExtensionActivation" --self-test', ci)
    self.assertNotIn(" --expect enabled", ci)
    self.assertNotIn(" --expect disabled", ci)

  def test_manual_steps_verify_both_states_and_inert_popup(self):
    guide = (SAFARI / "README.md").read_text(encoding="utf-8")
    self.assertIn("## Safari activation acceptance test (opener-0611)", guide)
    self.assertIn("--expect disabled", guide)
    self.assertIn("--expect enabled", guide)
    self.assertIn("Safari > Settings > Extensions", guide)
    self.assertIn("Not active", guide)
    self.assertIn("cannot scan, sanitize, or open PDF", guide)


if __name__ == "__main__":
  unittest.main()
