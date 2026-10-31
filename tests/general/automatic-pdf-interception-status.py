#!/usr/bin/env python3
"""Regression test for effective interception status separate from saved consent."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp/BrowsersSettingsView.swift"
POPUP = ROOT / "extensions/webextension/src/popup.html"
VALIDATOR = ROOT / "extensions/webextension/scripts/popup-assets.mjs"
CSS = ROOT / "extensions/webextension/src/popup.css"
MANIFEST = ROOT / "extensions/webextension/manifest.json"
BACKGROUND = ROOT / "extensions/webextension/src/background.js"


class AutomaticInterceptionEffectiveStatusTests(unittest.TestCase):
  def test_effective_state_is_prominent_and_independent_of_opt_in(self):
    view = VIEW.read_text(encoding="utf-8")
    section = view.split('GroupBox("Automatic PDF interception") {', 1)[1].split(
      'GroupBox("Browser downloads") {', 1
    )[0]
    self.assertIn('private let effectiveAutomaticInterceptionStatus = "Inactive"', view)
    self.assertIn('LabeledContent("Effective interception status", value: effectiveAutomaticInterceptionStatus)', section)
    self.assertIn('accessibilityIdentifier("automaticPDFInterceptionEffectiveStatus")', section)
    self.assertIn('LabeledContent("Interception status", value: effectiveAutomaticInterceptionStatus)', section)
    self.assertIn('accessibilityIdentifier("automaticPDFInterceptionEffectiveStatus-\\(browser.id)")', section)
    self.assertIn('ForEach(automaticInterceptionBrowsers) { browser in', section)
    self.assertIn('Toggle("Enable Automatic PDF Interception", isOn: Binding(', section)
    self.assertIn('automaticInterceptionOptIns[browser.id] ?? false', section)
    self.assertIn('Automatic interception is not active in any browser', section)
    self.assertIn('Saved', section)
    self.assertNotIn('value: automaticInterceptionOptIns', section)
    self.assertNotIn('effectiveAutomaticInterceptionStatus = optedIn', view)
    self.assertNotIn('effectiveAutomaticInterceptionStatus = enabled', view)
    # Status is a fixed read-only report of the current inert deployment,
    # not a preference write or a future activation switch.
    self.assertEqual(len(re.findall(r'effectiveAutomaticInterceptionStatus\s*=', view)), 1)
    for bad in ("permissions.request", "sendNativeMessage", "downloads.open",
                "scan-and-open", "webRequest", "declarativeNetRequest"):
      self.assertNotIn(bad, section)

  def test_popup_reports_specific_inactive_status_without_script_or_toggle(self):
    markup = POPUP.read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")
    styles = CSS.read_text(encoding="utf-8")
    self.assertIn('id="automaticInterceptionEffectiveStatus" role="status">Status: Inactive</p>', markup)
    self.assertIn('aria-labelledby="interception-state-title"', markup)
    self.assertIn('Saved opt-in preferences do not change this status.', markup)
    self.assertEqual(markup.count('id="automaticInterceptionEffectiveStatus"'), 1)
    self.assertEqual(markup.count('id="interception-state-title"'), 1)
    for protected in ("interceptionStatusSection", "interceptionStatusTitle",
                      "interceptionStatusValue", "interceptionStatusExplanation"):
      self.assertIn(f"content.split({protected}).length !== 2", validator)
      self.assertIn(f'.replace({protected}, "")', validator)
    self.assertIn('.interception-state [role="status"]', styles)
    self.assertIn('prefers-color-scheme: dark', styles)
    self.assertNotIn("<script", markup)
    self.assertNotIn('Status: Active', markup)

  def test_status_does_not_relax_extension_scanner_or_preferences(self):
    view = VIEW.read_text(encoding="utf-8")
    manifest = MANIFEST.read_text(encoding="utf-8")
    background = BACKGROUND.read_text(encoding="utf-8")
    self.assertIn('BrowserAutomaticPDFInterceptionPreference.saveOptIn(', view)
    self.assertIn('automaticInterceptionOptIns[browser.id] =', view)
    self.assertIn('selected PDF application', view)
    self.assertIn('"permissions": []', manifest)
    self.assertIn('"host_permissions": []', manifest)
    self.assertTrue(background.strip().endswith("void 0;"))


if __name__ == "__main__":
  unittest.main()
