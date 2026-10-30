#!/usr/bin/env python3
"""Test Browser Integration is a user-initiated, read-only local preflight."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "PDFMagicOpenerApp/BrowsersSettingsView.swift"
PREF = ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift"
CI = ROOT / ".github/workflows/ci.yml"

class BrowserIntegrationTestActionTests(unittest.TestCase):
  def test_action_is_accessible_and_only_runs_on_user_request(self):
    view = VIEW.read_text()
    for expected in (
        'GroupBox("Browser integration test")',
        'Button("Test Browser Integration") {',
        'accessibilityIdentifier("testBrowserIntegrationButton")',
        'accessibilityIdentifier("browserIntegrationTestSection")',
        'accessibilityIdentifier("browserIntegrationTestStatus")',
        'accessibilityIdentifier("browserIntegrationTestDetails")',
        'browserIntegrationTestReport = BrowserIntegrationTest.run(',
        'DefaultPDFBrowserPreferences.discover().map(\\.id)',
        'DefaultPDFBrowserPreferences.monitoringBrowserCatalog.map(\\.id)',
        'if let report = browserIntegrationTestReport {',
        'No authenticated browser-to-native scanner integration is active',
    ):
      with self.subTest(expected=expected):
        self.assertIn(expected, view)
    self.assertEqual(view.count('Button("Test Browser Integration")'), 1)
    # This explicit test is not automatically invoked on opening the page.
    self.assertNotIn('.onAppear(perform: testBrowserIntegration)', view)
    for forbidden in ("permissions.request", "downloads.open", "sendNativeMessage",
                      "requestAuthorization", "Process(", "NSWorkspace", "UserDefaults",
                      "target-app.txt", "clamscan(", "scan-and-open"):
      self.assertNotIn(forbidden, view)

  def test_local_report_cannot_claim_a_verified_scanner_connection(self):
    source = PREF.read_text()
    model = source.split("struct BrowserIntegrationTestReport: Equatable {", 1)[1].split(
        "// Read-only presentation of browser download monitoring.", 1
    )[0]
    for expected in (
        'var statusLabel: String { "Integration test unavailable" }',
        '"Detected \\(detectedCount) of \\(supportedCount) supported browsers. "',
        'No authenticated browser-to-native scanner integration is active',
        'This check cannot verify downloads, scanner connectivity, or safe opening.',
        'supportedIDs.filter { !$0.isEmpty }',
        'supported.filter { detectedIDs.contains($0) }.count',
    ):
      self.assertIn(expected, model)
    for forbidden in ("UserDefaults", "nativeMessaging", "permissions.request", "scannerHealthy",
                      "scanAvailable", "return true", "Process(", "NSWorkspace", "clamscan"):
      self.assertNotIn(forbidden, model)

  def test_ci_runs_portable_and_compiled_preflight_regressions(self):
    ci = CI.read_text()
    self.assertIn("tests/general/browser-integration-test.py -v", ci)
    self.assertIn("test-browser-integration.swift -o", ci)
    self.assertIn('"$RUNNER_TEMP/TestBrowserIntegration"', ci)
    # Existing safety and unrelated notification / monitoring tests remain.
    self.assertIn("tests/general/browser-monitoring-status.py -v", ci)
    self.assertIn("tests/general/download-scan-results.py -v", ci)

if __name__ == "__main__":
  unittest.main()
