#!/usr/bin/env python3
"""Guard native failed-scan notices against false positive and sensitive diagnostics."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PREF = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
OPENER = (ROOT / "brave-pdf-opener.swift").read_text()
SCANNER = (ROOT / "scan-and-open.py").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()

class FailedScanNotificationTests(unittest.TestCase):
  def test_only_exact_trusted_scan_failures_are_labeled(self):
    for required in ("enum FailedScanNotificationClassification",
                     "private static let verifiedFailures: Set<String>",
                     "return verifiedFailures.contains(failure)",
                     "BlockedFileNotificationPreference.shouldNotify(",
                     "The malware scan could not finish; opening was stopped.",
                     "The malware scan did not confirm a complete scan; opening was stopped.",
                     "The malware scan timed out; opening was stopped."):
      self.assertIn(required, PREF)
    self.assertIn("safe_scan_failure(error)", SCANNER)
    self.assertIn("print(f'Scan request {index}: {safe_scan_failure(error)}'", SCANNER)

  def test_path_free_notification_preserves_mandatory_failure_alert(self):
    for required in ("deliverBlockedFileNotification(malwareDetected: Bool, scanFailed: Bool",
                     "malwareDetected: blockedNotificationKind == .malwareDetected",
                     "Malware was detected. The PDF was blocked and was not opened.",
                     "FailedScanNotificationClassification.shouldShowFailedScanNotice(",
                     "A PDF scan failed or could not finish. The file was not opened.",
                     "A PDF could not be opened because its safety check failed.",
                     "center.getNotificationSettings",
                     "center.requestAuthorization(options: [.alert])",
                     "center.add(request)",
                     "if let failure = failure {", "alert.runModal()",
                     "SuccessfulScanNotificationPreference.shouldNotify(",
                     "process.terminationStatus != 0",
                     "self.pendingSuccessNotifications += 1",
                     "self.pendingSuccessNotifications -= 1"):
      self.assertIn(required, OPENER)
    notifier = OPENER.split("func deliverBlockedFileNotification(", 1)[1].split(
      "// A request's arrival time", 1)[0]
    for forbidden in ("requestedPaths", "lastPathComponent", "failure.localizedDescription",
                      "scanRequests", "NSAlert", "Process(", "FileManager"):
      self.assertNotIn(forbidden, notifier)

  def test_native_and_portable_ci_are_required(self):
    self.assertIn("tests/notifications/failed-scan.py -v", CI)
    self.assertIn("test-failed-scan-notifications.swift", CI)
    self.assertIn("brave-pdf-opener.swift scan-progress-view.swift PDFMagicOpenerApp/ScanProgressPreference.swift", CI)

if __name__ == "__main__":
  unittest.main()
