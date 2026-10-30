#!/usr/bin/env python3
"""Verify per-browser download monitoring status is truthful and read-only."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp/BrowsersSettingsView.swift"
CATALOG = ROOT / "PDFMagicOpenerApp/DefaultPDFBrowserPreferences.swift"
PREFERENCES = ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift"
CI = ROOT / ".github/workflows/ci.yml"

class BrowserMonitoringStatusTests(unittest.TestCase):
  def test_status_lists_supported_browsers_from_existing_verified_catalog(self):
    view = VIEW.read_text()
    catalog = CATALOG.read_text()
    for expected in (
        'GroupBox("Per-browser monitoring status")',
        'accessibilityIdentifier("perBrowserMonitoringStatusSection")',
        'ForEach(browserMonitoringRows) { browser in',
        'Text(browser.name)',
        'Text(browser.statusLabel)',
        'accessibilityIdentifier("browserMonitoringStatus-\\(browser.id)")',
        'DefaultPDFBrowserPreferences.monitoringBrowserCatalog',
        'DefaultPDFBrowserPreferences.discover().map(\\.id)',
        '.onAppear(perform: refreshBrowserMonitoringStatus)',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, view)
    self.assertIn('browserNames.map { (id: $0.0, name: $0.1) }', catalog)
    # One source of supported IDs, not an independent hardcoded list.
    browser_ids = re.findall(r'\("([^"]+)", "[^"]+"\)', catalog.split('private static let browserNames:', 1)[1].split('= [', 1)[1].split(']', 1)[0])
    self.assertEqual(len(browser_ids), 9)
    self.assertEqual(len(set(browser_ids)), 9)

  def test_no_live_status_claim_and_opt_in_never_enables_scanning(self):
    view = VIEW.read_text()
    prefs = PREFERENCES.read_text()
    model = prefs.split("struct BrowserMonitoringStatusRow:", 1)[1].split(
        "// Versioned, opt-in representation for settings shared", 1)[0]
    self.assertIn('detected ? "Not connected" : "Not detected"', model)
    self.assertNotIn('"Monitoring active"', model)
    self.assertNotIn('"Connected"', model)
    self.assertIn("seen.insert(browser.id).inserted", model)
    self.assertIn("Your download monitoring opt-in does not activate monitoring", view)
    # No browser-extension activation, permission grant or scanner bypass.
    for forbidden in ("permissions.request", "downloads.open", "download.onCreated",
                      "sendNativeMessage", "clamscan", "Process(", "NSWorkspace",
                      "UserDefaults", "target-app.txt"):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, view)
    for forbidden in ("UserDefaults", "scanner", "permission", "Process("):
      # Comments may describe why these cannot be used; executable body must
      # not mutate permissions, runtime scanner state or user defaults.
      body = model.split("enum BrowserMonitoringStatusDisplay {", 1)[1]
      self.assertNotIn(forbidden, body)

  def test_ci_exercises_both_portable_and_compiled_model(self):
    ci = CI.read_text()
    self.assertIn("tests/general/browser-monitoring-status.py -v", ci)
    self.assertIn("test-browser-monitoring-status.swift -o", ci)
    self.assertIn('"$RUNNER_TEMP/TestBrowserMonitoringStatus"', ci)

if __name__ == "__main__":
  unittest.main()
