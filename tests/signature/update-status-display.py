#!/usr/bin/env python3
"""opener-0380: Updates displays safe, read-only ClamAV timestamp status."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
VIEW = ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift"
READER = ROOT / "PDFMagicOpenerApp/SignatureUpdateStatus.swift"
PROJECT = ROOT / "PDFMagicOpener.xcodeproj/project.pbxproj"


class SignatureStatusDisplayTests(unittest.TestCase):
    def test_updates_view_displays_attempt_success_and_unknown_without_claiming_freshness(self):
        source = VIEW.read_text(encoding="utf-8")
        for required in (
            "SignatureUpdateStatus.readInstalled()",
            "signatureStatus.message",
            '"Last attempted update"',
            '"Last successful update"',
            '"Unavailable"',
            "Times are shown in your local time zone.",
            "do not verify signature freshness or database health",
            'accessibilityIdentifier("signatureUpdateSummary")',
            'accessibilityIdentifier("signatureUpdateLastAttempt")',
            'accessibilityIdentifier("signatureUpdateLastSuccess")',
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        for prohibited in ("FreshClam is up to date", "definitions are current",
                           "Update succeeded", "Update failed", "Scan is safe"):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, source)

    def test_reader_rejects_symlinked_nonregular_malformed_and_future_data(self):
        reader = READER.read_text(encoding="utf-8")
        for required in (
            "O_NOFOLLOW", "O_NONBLOCK", "fstat(", "S_IFREG",
            "count: 48", "regularExpression", "seconds.isFinite",
            "seconds <= now.timeIntervalSince1970",
            '"last-attempted-update"', '"last-successful-update"',
            "Latest attempt is not confirmed successful",
            "Successful update recorded; attempt history unavailable",
        ):
            with self.subTest(required=required):
                self.assertIn(required, reader)
        for prohibited in (
            "Process(", "URLSession", "downloadTask", "UserDefaults",
            "freshclam --", "write(to:", "removeItem", "createFile",
            "subprocess", "clamscan(", "signature_update_status.py",
        ):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, reader)

    def test_reader_is_compiled_into_app_and_native_tests_in_ci(self):
        project = PROJECT.read_text(encoding="utf-8")
        self.assertEqual(project.count("path = SignatureUpdateStatus.swift;"), 1)
        self.assertIn("B38000000000000000000001,", project)
        self.assertIn("B38000000000000000000002,", project)
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/run-test.py tests/signature/update-status-display.py -v", ci)
        self.assertIn("test-signature-update-status.swift", ci)
        self.assertIn("PDFMagicOpenerApp/SignatureUpdateStatus.swift", ci)
        self.assertIn("xcrun swiftc -parse-as-library -warnings-as-errors", ci)

    def test_no_change_to_updater_or_fail_closed_scan_gate(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn("'Label': 'local.studio.pdf-malware-signatures'", installer)
        self.assertIn("'StartInterval': 14400", installer)
        self.assertIn("'RunAtLoad': True", installer)
        gate = (ROOT / "scan-and-open.py").read_text()
        self.assertIn("MAX_DATABASE_AGE = 48 * 60 * 60", gate)
        self.assertNotIn("SignatureUpdateStatus", gate)
        self.assertNotIn("SignatureUpdateStatus", installer)


if __name__ == "__main__":
    unittest.main()
