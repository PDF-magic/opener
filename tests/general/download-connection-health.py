#!/usr/bin/env python3
"""Connection-health UI must never mistake transport or saved consent for scan readiness."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DownloadConnectionHealthTests(unittest.TestCase):
  def test_accessible_global_indicator_is_read_only_and_explicit(self):
    view = (ROOT / "PDFMagicOpenerApp/BrowsersSettingsView.swift").read_text()
    for required in (
        'GroupBox("Connection health")',
        'accessibilityIdentifier("browserNativeConnectionHealthIndicator")',
        'accessibilityIdentifier("browserNativeConnectionHealthDetail")',
        'accessibilityIdentifier("browserNativeConnectionHealthSection")',
        "BrowserNativeConnectionHealth.current.statusLabel",
        "BrowserNativeConnectionHealth.current.detail",
        "No permission is requested or scan started by this indicator",
        'GroupBox("Browser downloads")',
        'Toggle("Enable Browser Download Monitoring"',
    ):
      with self.subTest(required=required):
        self.assertIn(required, view)
    self.assertEqual(view.count('GroupBox("Connection health")'), 1)
    for forbidden in (
        "Process(", "NSWorkspace", "FileHandle(", "UserDefaults",
        "permissions.request", "sendNativeMessage", "downloads.open",
        "nativeMessaging", "requestAuthorization", "clamscan",
    ):
      with self.subTest(forbidden=forbidden):
        self.assertNotIn(forbidden, view)

  def test_connection_health_reports_only_verified_transport(self):
    source = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
    contract = source.split("enum BrowserNativeConnectionHealth: Equatable {", 1)[1].split(
        "// Download scan-result presentation only.", 1
    )[0]
    for required in (
        "static var current: BrowserNativeConnectionHealth { .notConnected }",
        'case .notConnected: return "Not connected"',
        'case .transportOnly: return "Host reachable — scanning unavailable"',
        "authenticatedSession, protocolVersion == 1,",
        'hostStatus == "transport-only", !scanAvailable',
        "var scannerConnectionHealthy: Bool { false }",
        "No authenticated browser-to-native connection is active",
    ):
      self.assertIn(required, contract)
    for forbidden in (
        "UserDefaults", "scan-and-open", "clamscan", "Process(",
        "NSWorkspace", "requestAuthorization", "permissions.request",
        "selectedProtectionProfile", "return true",
    ):
      self.assertNotIn(forbidden, contract)

  def test_native_host_and_extension_cannot_claim_scanner_connection(self):
    host = (ROOT / "native-messaging/HostStatus.swift").read_text()
    background = (ROOT / "extensions/webextension/src/background.js").read_text()
    manifest = (ROOT / "extensions/webextension/manifest.json").read_text()
    self.assertIn('"status": "transport-only"', host)
    self.assertIn('"scanAvailable": false', host)
    self.assertTrue(background.strip().endswith("void 0;"))
    self.assertIn('"permissions": []', manifest)
    self.assertNotIn('"nativeMessaging"', manifest)

  def test_ci_executes_native_contract_in_addition_to_source_guard(self):
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    self.assertIn("tests/general/download-connection-health.py -v", workflow)
    self.assertIn("test-download-connection-health.swift", workflow)
    self.assertIn(
        "PDFMagicOpenerApp/ScanProgressPreference.swift test-download-connection-health.swift",
        workflow,
    )


if __name__ == "__main__":
  unittest.main()
