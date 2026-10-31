#!/usr/bin/env python3
"""Check the reusable native scan result summary without weakening scan gates."""
from pathlib import Path
import re
import unittest

from scan_results import ScanResultStatus

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scan-result-summary-view.swift"
SWIFT_TEST = ROOT / "test-scan-result-summary.swift"
CI = ROOT / ".github/workflows/ci.yml"


class ScanResultSummaryComponentTests(unittest.TestCase):
    def test_matches_the_exact_canonical_status_vocabulary(self):
        source = SOURCE.read_text(encoding="utf-8")
        enum_body = source.split("enum ScanResultSummaryStatus: String, CaseIterable {", 1)[1].split("}", 1)[0]
        cases = re.findall(r"^\s*case (\w+)\s*$", enum_body, flags=re.MULTILINE)
        self.assertEqual(cases, [status.value for status in ScanResultStatus])
        self.assertEqual(len(cases), 10)

    def test_reusable_native_view_has_safe_unknown_and_failure_states(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("final class ScanResultSummaryView: NSView", source)
        self.assertIn("func show(", source)
        self.assertIn("_ status: ScanResultSummaryStatus?", source)
        self.assertIn("func reset()", source)
        self.assertIn("show(nil)", source)
        self.assertIn('heading: "No verified scan result"', source)
        self.assertIn('heading: "Scan failed"', source)
        self.assertIn('heading: "Scan complete"', source)
        self.assertIn("Opening was stopped.", source)
        self.assertIn("setAccessibilityIdentifier", source)
        self.assertIn("NSStackView", source)
        for forbidden in ("Process(", "NSWorkspace.shared.open", "remove_quarantine(",
                          "UserDefaults", "scan-and-open.py", "subprocess", "NSAlert("):
            self.assertNotIn(forbidden, source)

    def test_only_fixed_copy_is_rendered_without_paths_or_untrusted_diagnostics(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("let copy = ScanResultSummaryCopy.forStatus(status)", source)
        self.assertIn("headingLabel.stringValue = copy.heading", source)
        self.assertIn("explanationLabel.stringValue = copy.explanation", source)
        self.assertNotIn("func show(_ status: String)", source)
        self.assertNotIn("scannerOutput", source)
        self.assertIn("documentURL: URL? = nil", source)
        self.assertIn("selectedProtectionLevel: ScanResultSummaryProtectionLevel? = nil", source)
        self.assertIn("url.isFileURL", source)
        self.assertIn("url.lastPathComponent", source)
        self.assertIn("CharacterSet.controlCharacters.contains", source)
        self.assertIn("bidiControls.contains", source)
        self.assertIn('Document: Unavailable', source)
        self.assertIn('Selected protection level: Unavailable', source)
        self.assertIn("preview only; Built-in scanning remains active", source)
        self.assertIn('documentNameLabel.setAccessibilityLabel', source)
        self.assertIn('selectedProtectionLevelLabel.setAccessibilityLabel', source)
        self.assertNotIn("UserDefaults", source)
        self.assertNotIn("scannerOutput", source)
        self.assertIn("private(set) var displayedStatus", source)

    def test_ci_compiles_and_exercises_the_component_on_macos(self):
        workflow = CI.read_text(encoding="utf-8")
        self.assertIn("python3 tests/scan/result-summary-component.py -v", workflow)
        self.assertIn("scan-result-summary-view.swift test-scan-result-summary.swift", workflow)
        self.assertIn('"$RUNNER_TEMP/TestScanResultSummary"', workflow)
        harness = SWIFT_TEST.read_text(encoding="utf-8")
        self.assertIn("@main", harness)
        self.assertIn("ScanResultSummaryStatus.allCases", harness)
        self.assertIn("first.reset()", harness)
        self.assertIn("second.show(.scanFailed, documentURL:", harness)
        self.assertIn("first.displayedProtectionLevel == nil", harness)
        self.assertIn('Document: März résumé 🦄.pdf', harness)
        self.assertIn('URL(string: "https://example.invalid/secret.pdf")', harness)
        self.assertIn("preview only", harness)


if __name__ == "__main__":
    unittest.main()
