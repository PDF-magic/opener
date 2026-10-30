#!/usr/bin/env python3
"""opener-0392: Warn visibly when the installed signature-update stamp is too old."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "PDFMagicOpenerApp/SignatureUpdateStatus.swift"
VIEW = ROOT / "PDFMagicOpenerApp/UpdatesSettingsView.swift"


class StaleSignatureWarningTests(unittest.TestCase):
    def test_warning_matches_exact_existing_inclusive_48_hour_scan_gate(self):
        model = MODEL.read_text()
        scanner = (ROOT / "scan-and-open.py").read_text()
        self.assertRegex(scanner, r"MAX_DATABASE_AGE\s*=\s*48\s*\*\s*60\s*\*\s*60")
        self.assertRegex(model, r"maximumSignatureAge:\s*TimeInterval\s*=\s*48\s*\*\s*60\s*\*\s*60")
        self.assertIn("age > Self.maximumSignatureAge", model)
        self.assertIn("age.isFinite, age >= 0", model)
        self.assertIn("more than 48 hours old", model)
        self.assertIn("Scanner freshness checks remain enforced", model)
        self.assertIn("Signature freshness cannot be verified", model)
        self.assertIn("last-successful-update", model)
        self.assertIn("O_NOFOLLOW", model)
        self.assertNotIn("Process(", model)

    def test_updates_displays_accessible_warning_and_refreshes_during_auto_updates(self):
        view = VIEW.read_text()
        self.assertIn("SignatureUpdateStatus.readInstalled(now: timeline.date)", view)
        self.assertIn(".freshnessWarning(now: timeline.date)", view)
        self.assertIn('accessibilityIdentifier("signatureFreshnessWarning")', view)
        self.assertIn('systemImage: "exclamationmark.triangle.fill"', view)
        self.assertIn("TimelineView(.periodic(from: .now, by: 60))", view)
        self.assertIn('Button("Update Signatures Now")', view)
        self.assertIn('accessibilityIdentifier("signatureUpdateSummary")', view)
        self.assertNotIn("onAppear", view)
        self.assertNotIn("setDefault", view)

    def test_native_age_boundary_is_in_macos_ci_and_linux_guard(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("python3 tests/general/stale-signature-warning.py -v", ci)
        self.assertIn("test-stale-signature-warning.swift", ci)
        self.assertIn("xcrun swiftc -parse-as-library -warnings-as-errors", ci)
        native = (ROOT / "test-stale-signature-warning.swift").read_text()
        self.assertIn("48 * 60 * 60 + 1", native)
        self.assertIn("48 * 60 * 60]", native)
        self.assertIn("cannot be verified", native)
        self.assertIn("createSymbolicLink", native)
        self.assertIn("addingTimeInterval(-20)", native)

    def test_scan_gate_agent_and_customization_are_unchanged(self):
        installer = (ROOT / "install-allow-and-open.sh").read_text()
        self.assertIn("'StartInterval': 14400", installer)
        self.assertIn("'RunAtLoad': True", installer)
        gate = (ROOT / "scan-and-open.py").read_text()
        self.assertNotIn("freshnessWarning", gate)
        updater = (ROOT / "update-malware-signatures.sh").read_text()
        self.assertNotIn("freshnessWarning", updater)
        self.assertIn("last-successful-update", updater)


if __name__ == "__main__":
    unittest.main()
