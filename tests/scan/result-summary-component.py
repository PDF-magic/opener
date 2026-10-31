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
        self.assertIn('let malwareStatusLabel = NSTextField(labelWithString: "Malware: Not determined")', source)
        self.assertIn('malwareStatus = "Malware: Detected"', source)
        self.assertIn('malwareStatus = "Malware: Not detected"', source)
        self.assertIn('malwareStatus = "Malware: Not determined"', source)
        self.assertIn("malwareStatusLabel.stringValue = malwareStatus", source)
        self.assertIn("malwareStatusLabel.setAccessibilityLabel(malwareStatus)", source)
        self.assertIn('setAccessibilityIdentifier("scanResultSummaryMalware")', source)
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
        self.assertIn("sanitization: ScanResultSummarySanitization? = nil", source)
        self.assertIn("enum ScanResultSummarySanitization: String, CaseIterable", source)
        self.assertIn('return "Sanitization: Performed"', source)
        self.assertIn('return "Sanitization: Not performed"', source)
        self.assertIn('"Sanitization: Unavailable"', source)
        self.assertIn("sanitization?.displayText", source)
        self.assertIn("displayedSanitization = sanitization", source)
        self.assertIn("sanitizationLabel.setAccessibilityLabel", source)
        self.assertNotIn("selectedProtectionLevel == .maximum", source)
        self.assertNotIn("status == .clean", source)
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
        self.assertIn("private(set) var technicalDetailsExpanded", source)
        self.assertIn("ScanResultSummaryTechnicalCopy.forStatus(status)", source)
        self.assertIn("technicalDetailsButton.isHidden = technicalCopy == nil", source)
        self.assertIn("technicalDetailsLabel.setAccessibilityLabel(technicalCopy ??", source)
        self.assertIn('case .clean, .cancelled:', source)
        self.assertIn("technicalDetailsExpanded = false", source)
        self.assertIn("#selector(toggleTechnicalDetails(_:))", source)
        self.assertIn("invalidateIntrinsicContentSize()", source)
        self.assertNotIn("scannerOutput", source)

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
        self.assertIn("first.technicalDetailsButton.performClick(nil)", harness)
        self.assertIn("second.technicalDetailsButton.performClick(nil)", harness)
        self.assertIn("first.technicalDetailsLabel.isHidden", harness)
        self.assertIn("second.show(nil)", harness)
        self.assertIn("technicalDetailsButton.accessibilityLabel()", harness)
        self.assertIn("sanitization: .performed", harness)
        self.assertIn("sanitization: .notPerformed", harness)
        self.assertIn('ScanResultSummarySanitization(rawValue: "attempted") == nil', harness)
        self.assertIn("first.displayedSanitization == nil", harness)
        self.assertIn("second.sanitizationLabel.stringValue", harness)
        self.assertIn("for status in ScanResultSummaryStatus.allCases", harness)
        self.assertIn('status == .malwareDetected ? "Malware: Detected"', harness)
        self.assertIn('status == .clean ? "Malware: Not detected" : "Malware: Not determined"', harness)
        self.assertIn('first.malwareStatusLabel.stringValue == "Malware: Not determined"', harness)
        self.assertIn('second.malwareStatusLabel.stringValue == "Malware: Not determined"', harness)


if __name__ == "__main__":
    unittest.main()
