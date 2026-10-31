#!/usr/bin/env python3
"""Guard duplicate notification delivery without changing the required scan gate."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
OPENER = (ROOT / "brave-pdf-opener.swift").read_text()
PREF = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()


class NotificationDeduplicationTests(unittest.TestCase):
  def test_opaque_stable_per_document_outcome_identifiers(self):
    self.assertIn("SHA256.hash(data: Data(path.utf8))", OPENER)
    self.assertIn('return "pdf-magic-opener.scan.', OPENER)
    self.assertNotIn("UUID().uuidString", OPENER.split(
      "private func deliverScanNotification", 1)[1].split(
      "// A request's arrival time", 1)[0])
    for outcome in ('"success"', '"malware"', '"failed"', '"blocked"'):
      self.assertIn(outcome, OPENER)
    self.assertIn("scanNotificationIdentifier(path: path, kind:", OPENER)

  def test_current_and_pending_notifications_are_coalesced(self):
    self.assertIn("center.getDeliveredNotifications", OPENER)
    self.assertIn("center.getPendingNotificationRequests", OPENER)
    self.assertIn("ScanNotificationDeduplication.shouldQueue(", OPENER)
    self.assertIn("self.notificationReservations.reserve(identifier)", OPENER)
    self.assertIn("let request = UNNotificationRequest(identifier: identifier", OPENER)
    self.assertIn("static let repeatWindow: TimeInterval = 30", PREF)
    self.assertIn("age >= 0 && age < repeatWindow", PREF)
    self.assertIn("private let lock = NSLock()", PREF)
    self.assertNotIn("defaults.set(", PREF.split("// Presentation-only duplicate suppression.",1)[1].split(
      "// Opt-in presentation only",1)[0])

  def test_blocking_permission_and_preference_boundaries(self):
    self.assertIn("received.insert(path).inserted", OPENER)
    self.assertIn("if process.terminationStatus != 0 {", OPENER)
    self.assertIn("if let failure = failure {", OPENER)
    self.assertIn("alert.runModal()", OPENER)
    self.assertIn("SuccessfulScanNotificationPreference.shouldNotify(", OPENER)
    self.assertIn("BlockedFileNotificationPreference.notificationKind(", OPENER)
    self.assertIn("self.cancelledRequests.contains(path)", OPENER)
    self.assertIn("center.requestAuthorization(options: [.alert])", OPENER)
    self.assertIn("default:", OPENER)
    self.assertIn("completion()", OPENER)
    notifier = OPENER.split("private func deliverScanNotification(", 1)[1].split(
      "// A request's arrival time", 1)[0]
    for private_value in ("requestedPaths", "lastPathComponent", "failure.localizedDescription",
                          "FileManager", "scanRequests", "NSAlert"):
      self.assertNotIn(private_value, notifier)

  def test_both_ci_suites_run_behavioral_regressions(self):
    self.assertIn("tests/notifications/deduplication.py -v", CI)
    self.assertIn("test-notification-deduplication.swift", CI)


if __name__ == "__main__":
  unittest.main()
