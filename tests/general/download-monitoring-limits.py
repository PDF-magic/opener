#!/usr/bin/env python3
"""Check that the Browsers page explains monitoring's boundaries honestly."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "PDFMagicOpenerApp"
VIEW = APP / "BrowsersSettingsView.swift"
WORKFLOW = ROOT / ".github/workflows/ci.yml"


class DownloadMonitoringLimitsTests(unittest.TestCase):
  def test_visible_accessible_explanation_has_distinct_protection_boundaries(self):
    source = VIEW.read_text(encoding="utf-8")
    beginning = 'GroupBox("What monitoring can and cannot prevent")'
    end = 'GroupBox("Additional applications")'
    self.assertEqual(source.count(beginning), 1)
    content = source.split(beginning, 1)[1].split(end, 1)[0]
    for expected in (
        'accessibilityIdentifier("downloadMonitoringCapabilitiesAndLimitsSection")',
        'Text("What monitoring does today")',
        'Text("What a verified integration could protect")',
        'Text("What monitoring cannot guarantee")',
        "Browser download monitoring is not active",
        "Turning on the preference does not inspect downloaded files",
        "block browser automatic opening",
        "download history",
        "separate browser permission and an authenticated native scanner connection",
        "supported and fully available downloads could be scanned",
        "before a PDF Magic Opener handoff",
        "A detected threat, failed scan, or incomplete check must never authorize",
        "installed PDF Magic Opener already have an independent scan-before-open gate",
        "browser's built-in PDF viewer",
        "Finder or another application",
        "separately integrated with verified scan enforcement",
        "cannot guarantee detection of every threat",
        "retroactively protect a file already opened",
        "An alert is not a block",
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, content)

    # Text-only: never launch a download, ask for permissions, or alter a
    # security gate or the user's preferences from this explanation.
    for forbidden in ("Toggle(", "Button(", "Picker(", "Binding(",
                      "UserDefaults", "Process(", "NSWorkspace", "FileHandle(",
                      "requestAuthorization", "downloads.open",
                      "permissions.request", "sendNativeMessage", "onAppear("):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, content)
    self.assertLess(source.index('GroupBox("Browser downloads")'), source.index(beginning))
    self.assertLess(source.index(beginning), source.index(end))

  def test_existing_controls_and_inactive_browser_integration_are_unchanged(self):
    view = VIEW.read_text(encoding="utf-8")
    for label in ("Show Scan Results", "Scan Other Supported Files",
                  "Enable Browser Download Monitoring", "Show Only Warnings",
                  "Notify on Failed Scan"):
      with self.subTest(label=label):
        self.assertEqual(view.count(f'Toggle("{label}"'), 1)
    self.assertIn('GroupBox("Per-browser monitoring status")', view)
    self.assertIn('GroupBox("Connection health")', view)
    self.assertIn("BrowserDownloadMonitoringPreference.save(enabled)", view)

    background = (ROOT / "extensions/webextension/src/background.js").read_text()
    manifest = (ROOT / "extensions/webextension/manifest.json").read_text()
    host = (ROOT / "native-messaging/HostStatus.swift").read_text()
    self.assertTrue(background.strip().endswith("void 0;"))
    self.assertIn('"permissions": []', manifest)
    self.assertNotIn('"nativeMessaging"', manifest)
    self.assertIn('"status": "transport-only"', host)
    self.assertIn('"scanAvailable": false', host)

  def test_ci_runs_limits_regression(self):
    workflow = WORKFLOW.read_text(encoding="utf-8")
    self.assertEqual(workflow.count("tests/general/download-monitoring-limits.py -v"), 1)
    self.assertIn("tests/general/download-connection-health.py -v", workflow)
    self.assertIn("tests/general/browser-monitoring-status.py -v", workflow)


if __name__ == "__main__":
  unittest.main()
