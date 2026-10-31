#!/usr/bin/env python3
"""Guard optional Maximum sanitizer notifications without activating Maximum."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
PANEL = (ROOT / "scan-progress-view.swift").read_text()
OPENER = (ROOT / "brave-pdf-opener.swift").read_text()
PREFERENCES = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
SWIFT_HARNESS = (ROOT / "tests/scan/progress-component.py").read_text()
CI = (ROOT / ".github/workflows/ci.yml").read_text()
SCANNER = (ROOT / "scan-and-open.py").read_text()


class SanitizerFailureNotificationTests(unittest.TestCase):
    def test_only_validated_sanitizer_reports_trigger_once_per_request(self):
        self.assertIn('payload["status"] as? String == "sanitizerFailure"', PANEL)
        self.assertIn('payload["scanVerdict"] as? String == "notAssessed"', PANEL)
        self.assertIn('payload["permitsOpen"] as? Bool == false', PANEL)
        self.assertIn('let snapshot = MaximumSanitizationFailureSnapshot.decode(report)', PANEL)
        self.assertIn('if snapshot != nil && !maximumSanitizationFailureNotified {', PANEL)
        self.assertIn('onVerifiedMaximumSanitizationFailure?()', PANEL)
        self.assertIn('maximumSanitizationFailureNotified = false', PANEL)
        self.assertIn('maximumSanitizationFailureNotified = true', PANEL)
        for fragment in (
            'var sanitizerNotices = 0',
            'precondition(sanitizerNotices == 1, "The same failure must not notify twice")',
            'precondition(sanitizerNotices == 1, "Forged failures cannot notify")',
            'precondition(sanitizerNotices == 2, "A fresh verified failure may notify again")',
        ):
            self.assertIn(fragment, SWIFT_HARNESS)

    def test_delivery_is_opt_in_specific_private_and_best_effort(self):
        self.assertIn('newPanel.onVerifiedMaximumSanitizationFailure = { [weak self] in', OPENER)
        self.assertIn('guard let self, BlockedFileNotificationPreference.isEnabled() else { return }', OPENER)
        self.assertIn('deliverBlockedFileNotification(malwareDetected: false, sanitizerFailed: true)', OPENER)
        self.assertIn('sanitizerFailed: Bool = false', OPENER)
        self.assertIn('PDF sanitization failed. No sanitized copy was produced. This is not a malware detection.', OPENER)
        self.assertIn('Malware was detected. The PDF was blocked and was not opened.', OPENER)
        self.assertIn('content.title = "PDF Magic Opener"', OPENER)
        self.assertIn('center.getNotificationSettings', OPENER)
        self.assertIn('center.requestAuthorization(options: [.alert])', OPENER)
        self.assertIn('center.add(request)', OPENER)
        self.assertIn('self.pendingSuccessNotifications += 1', OPENER)
        self.assertIn('self.pendingSuccessNotifications -= 1', OPENER)
        self.assertIn('return false', PREFERENCES)  # blocked notices default off
        self.assertIn('static let key = "showBlockedFileNotifications"', PREFERENCES)
        delivery = OPENER.split("func deliverBlockedFileNotification(", 1)[1].split(
            "// A request's arrival time", 1)[0]
        for forbidden in ("filename", "requestedPaths", "lastPathComponent", "NSAlert",
                          "FileManager", "Process(", "failure.localizedDescription"):
            self.assertNotIn(forbidden, delivery)

    def test_does_not_change_scanner_or_automatic_maximum_policy(self):
        self.assertNotIn("attempt_sanitized_pdf_copy", SCANNER)
        self.assertIn("if process.terminationStatus != 0 {", OPENER)
        self.assertIn("alert.runModal()", OPENER)
        self.assertIn("MaximumSanitizationFailureSnapshot.decode(report)", PANEL)
        self.assertIn('tests/notifications/sanitizer-failure.py -v', CI)
        self.assertIn('PYTHONPATH=. python3 tests/scan/progress-component.py -v', CI)


if __name__ == "__main__":
    unittest.main()
