#!/usr/bin/env python3
"""Check that browser-specific interception opt-ins never imply active protection."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp" / "BrowsersSettingsView.swift"
STORE = ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift"
MATRIX = ROOT / "extensions/webextension/src/automatic-interception-capability-matrix.js"


class AutomaticPDFInterceptionOptionTests(unittest.TestCase):
  def test_opt_in_is_visible_only_for_installed_documented_api_browsers(self):
    view = VIEW.read_text(encoding="utf-8")
    store = STORE.read_text(encoding="utf-8")
    matrix = MATRIX.read_text(encoding="utf-8")

    self.assertIn('GroupBox("Automatic PDF interception")', view)
    self.assertIn('Toggle("Enable Automatic PDF Interception", isOn: Binding(', view)
    self.assertIn('ForEach(automaticInterceptionBrowsers)', view)
    self.assertIn("DefaultPDFBrowserPreferences.discover()", view)
    self.assertIn("eligibleBrowserIDs(", view)
    self.assertIn("installed.filter { supported.contains($0.id) }", view)
    self.assertIn('accessibilityIdentifier("automaticPDFInterceptionSection")', view)
    self.assertIn('accessibilityIdentifier("enableAutomaticPDFInterceptionToggle-', view)
    self.assertIn(".onAppear(perform: refreshAutomaticInterceptionOptions)", view)
    self.assertIn("set: { updateAutomaticInterceptionOptIn($0, browserID: browser.id) }", view)

    ids = re.search(r"static let candidateBrowserIDs: Set<String> = \[(.*?)\]", store, re.S)
    self.assertIsNotNone(ids)
    self.assertEqual(set(re.findall(r'"([^"]+)"', ids.group(1))), {
      "com.google.Chrome", "com.microsoft.edgemac", "org.mozilla.firefox"
    })
    for browser in ('"chrome"', '"edge"', '"firefox"'):
      self.assertIn(browser, matrix)
    self.assertNotIn('"com.apple.Safari"', ids.group(1))
    self.assertIn("CFGetTypeID(raw) == CFBooleanGetTypeID()", store)

  def test_opt_in_never_activates_interception_or_changes_other_preferences(self):
    view = VIEW.read_text(encoding="utf-8")
    store = STORE.read_text(encoding="utf-8")
    bg = (ROOT / "extensions/webextension/src/background.js").read_text(encoding="utf-8")
    shared = (ROOT / "extensions/webextension/manifest.json").read_text(encoding="utf-8")
    for phrase in (
      "Automatic interception is not active in any browser",
      "not request browser permissions", "selected PDF application",
      "Automatic interception remains inactive",
      "no change was saved",
      "previous choice is unchanged",
    ):
      self.assertIn(phrase, view)
    for forbidden in ("permissions.request", "sendNativeMessage", "scan-and-open",
                      "downloads.open", "addListener(", "webRequest", "declarativeNetRequest"):
      self.assertNotIn(forbidden, view)
    self.assertIn('static let key = "automaticPDFInterceptionOptIns"', store)
    self.assertIn("guard candidateBrowserIDs.contains(browserID)", store)
    self.assertIn("if let previous { defaults.set(previous, forKey: key) }", store)
    self.assertTrue(bg.strip().endswith("void 0;"))
    self.assertIn('"host_permissions": []', shared)
    self.assertIn('"permissions": []', shared)


if __name__ == "__main__":
  unittest.main()
