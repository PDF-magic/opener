#!/usr/bin/env python3
"""Compile the reusable native progress UI and verify opener-independent rendering."""
from pathlib import Path
import subprocess
import tempfile
import unittest

COMPONENT = (Path(__file__).resolve().parents[2] / "scan-progress-view.swift")


class ScanProgressComponentTests(unittest.TestCase):
    def test_malware_assessment_is_validated_and_used_in_the_display_label(self):
        source = COMPONENT.read_text()
        self.assertIn('private static let malwareAssessments = [', source)
        self.assertIn('let malwareAssessmentLabel: String', source)
        self.assertIn('· \\(malwareAssessmentLabel)', source)
        self.assertNotIn('· Malware not confirmed")', source)

    def test_maximum_failure_labels_match_canonical_reports(self):
        # Parse the authoritative Python definitions without importing optional
        # PDF raster dependencies that are not installed for native UI tests.
        import ast

        module = ast.parse(COMPONENT.with_name("maximum_sanitized_copy.py").read_text())
        kinds = next(
            node for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == "SanitizerFailureKind"
        )
        values = {
            assignment.targets[0].id: ast.literal_eval(assignment.value)
            for assignment in kinds.body
            if isinstance(assignment, ast.Assign)
            and isinstance(assignment.targets[0], ast.Name)
        }
        report = next(
            node.value for node in module.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_FAILURE_MESSAGES"
                    for target in node.targets)
        )
        messages = {
            values[key.attr]: ast.literal_eval(value)
            for key, value in zip(report.keys, report.values)
        }
        self.assertEqual(len(messages), 8)
        source = COMPONENT.read_text()
        for kind, message in messages.items():
            with self.subTest(kind=kind):
                self.assertIn(f'"{kind}": "{message}"', source)
        self.assertIn('payload["status"] as? String == "sanitizerFailure"', source)
        self.assertIn('payload["scanVerdict"] as? String == "notAssessed"', source)
        self.assertIn('payload["permitsOpen"] as? Bool == false', source)

    def test_existing_native_progress_panel_can_be_used_without_pdf_opener(self):
        source = COMPONENT.read_text()
        self.assertIn("final class ScanProgressPanel: NSPanel", source)
        self.assertNotIn("scan-and-open.py", source)
        self.assertNotIn("Process()", source)
        with tempfile.TemporaryDirectory(prefix="opener-scan-progress-") as directory:
            root = Path(directory)
            (root / "twilight-reading.png").write_bytes(
                (Path(__file__).resolve().parents[2] / "twilight-reading.png").read_bytes())
            harness = root / "test.swift"
            harness.write_text(source + """
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
final class CancelOwner: NSObject {
    var pressed = false
    @objc func cancel(_ sender: NSButton) { pressed = true }
}
let owner = CancelOwner()
let panel = ScanProgressPanel(cancelTarget: owner, cancelAction: #selector(CancelOwner.cancel(_:)))
precondition(panel.title == "PDF Magic Opener — Scanning")
precondition(!panel.hidesOnDeactivate && panel.level == .floating)
precondition(panel.progressIndicator.isIndeterminate)
precondition(panel.cancelButton.title == "Cancel")
precondition(panel.protectionProfileLabel.stringValue == "Active protection profile: Built-in")
precondition(panel.protectionProfileDetailsLabel.stringValue == "ClamAV malware scanning · fail-closed")
precondition(panel.protectionProfileLabel.accessibilityLabel() == "Active protection profile: Built-in")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.protectionProfileLabel }) == true)
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.protectionProfileDetailsLabel }) == true)
precondition(panel.protectionProfileLabel.frame.minY > panel.progressIndicator.frame.maxY)
precondition(panel.filenameLabel.frame.minY > panel.protectionProfileLabel.frame.maxY)
precondition(panel.activeScansLabel.stringValue == "Active scans: 0")
precondition(panel.activeScansLabel.accessibilityLabel() == "Active scans: 0")
precondition(panel.activeScansLabel.accessibilityIdentifier() == "activeScanCount")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.activeScansLabel }) == true)
precondition(panel.activeScansLabel.frame.minY > panel.protectionProfileLabel.frame.maxY)
precondition(panel.queuedDocumentCountLabel.stringValue == "0 documents queued")
precondition(panel.queuedDocumentCountLabel.accessibilityLabel() == "0 documents queued")
precondition(panel.queuedDocumentCountLabel.accessibilityIdentifier() == "queuedDocumentCount")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.queuedDocumentCountLabel }) == true)
precondition(panel.queuedDocumentCountLabel.frame.minY > panel.protectionProfileLabel.frame.maxY)
precondition(panel.activeScansLabel.frame.minY > panel.queuedDocumentCountLabel.frame.maxY)
precondition(panel.filenameLabel.frame.minY > panel.activeScansLabel.frame.maxY)
precondition(panel.stageLabel.stringValue == ScanProgressStage.queued.label)
precondition(panel.stageLabel.accessibilityLabel() == "Current scanning stage")
precondition(panel.contentView?.subviews.contains(where: { $0 is TwilightReadingView }) == true)
panel.updateBatchProgress((completed: 0, total: 1))
precondition(panel.progressIndicator.isIndeterminate)
panel.updateBatchProgress((completed: 0, total: 2))
precondition(!panel.progressIndicator.isIndeterminate)
precondition(panel.progressIndicator.minValue == 0)
precondition(panel.progressIndicator.maxValue == 2)
precondition(panel.progressIndicator.doubleValue == 0)
panel.updateBatchProgress((completed: 1, total: 2))
precondition(panel.progressIndicator.doubleValue == 1)
precondition(panel.progressIndicator.accessibilityLabel()
             == "1 of 2 document requests processed")
panel.updateBatchProgress((completed: 3, total: 2))
precondition(panel.progressIndicator.isIndeterminate)
panel.updateBatchProgress(nil)
precondition(panel.progressIndicator.isIndeterminate)
precondition(panel.progressIndicator.accessibilityLabel()
             == "Individual scan progress is unknown")
panel.show(documentDescription: "folder/Unicode – report.pdf", stage: .starting,
           queuedDocumentCount: 1, activeScans: 0)
precondition(panel.queuedDocumentCountLabel.stringValue == "1 document queued")
precondition(panel.activeScansLabel.stringValue == "Active scans: 0")
precondition(panel.filenameLabel.stringValue == "folder/Unicode – report.pdf")
precondition(panel.stageLabel.stringValue == "Starting safety checks…")
panel.show(documentDescription: "3 documents", stage: .scanning,
           queuedDocumentCount: 3, activeScans: 1)
precondition(panel.queuedDocumentCountLabel.stringValue == "3 documents queued")
precondition(panel.queuedDocumentCountLabel.accessibilityLabel() == "3 documents queued")
precondition(panel.activeScansLabel.stringValue == "Active scans: 1")
panel.show(documentDescription: "3 documents", stage: .scanning, activeScans: 2)
precondition(panel.activeScansLabel.stringValue == "Active scans: 2")
precondition(panel.activeScansLabel.accessibilityLabel() == "Active scans: 2")
precondition(panel.filenameLabel.stringValue == "3 documents")
panel.show(documentDescription: "last.pdf", stage: .starting,
           queuedDocumentCount: 0, activeScans: 0)
precondition(panel.queuedDocumentCountLabel.stringValue == "0 documents queued")
precondition(panel.activeScansLabel.stringValue == "Active scans: 0")
precondition(panel.filenameLabel.stringValue == "last.pdf")
panel.show(documentDescription: "3 documents", stage: .scanning, activeScans: 2)
precondition(panel.protectionProfileLabel.stringValue == "Active protection profile: Built-in")
precondition(panel.protectionProfileDetailsLabel.stringValue == "ClamAV malware scanning · fail-closed")
precondition(panel.stageLabel.stringValue == "Scanning and verifying document…")
precondition(panel.destinationBrowserLabel.stringValue == "Destination browser: Unavailable")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.destinationBrowserLabel }) == true)
precondition(panel.destinationBrowserLabel.frame.minY > panel.progressIndicator.frame.maxY)
precondition(panel.filenameLabel.frame.minY > panel.destinationBrowserLabel.frame.maxY)

let fixture = FileManager.default.temporaryDirectory
    .appendingPathComponent("selected-browser-\\(UUID().uuidString)", isDirectory: true)
try FileManager.default.createDirectory(at: fixture, withIntermediateDirectories: true)
let preference = fixture.appendingPathComponent("target-app.txt")
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Brave",
             "missing preferences must use the established Brave default")
try "com.google.Chrome\\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Google Chrome")
panel.updateDestinationBrowser(SelectedDestinationBrowser.displayName(in: fixture))
precondition(panel.destinationBrowserLabel.stringValue == "Destination browser: Google Chrome")
precondition(panel.destinationBrowserLabel.accessibilityLabel() == "Destination browser: Google Chrome")
try "system-default-browser\\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "System default browser")
try "org.mozilla.firefox\\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Firefox")
try "com.example.viewer\\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) ==
             "Custom application (com.example.viewer)", "custom selection must not be overwritten")
for invalid in ["local.studio.brave-pdf-opener", "bad..identifier", "invalid path", ""] {
    try invalid.write(to: preference, atomically: true, encoding: .ascii)
    precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Unavailable",
                 "invalid identifiers must never appear as selected browsers")
}
try FileManager.default.removeItem(at: preference)
let elsewhere = fixture.appendingPathComponent("elsewhere")
try "com.apple.Safari\\n".write(to: elsewhere, atomically: true, encoding: .ascii)
try FileManager.default.createSymbolicLink(at: preference, withDestinationURL: elsewhere)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Unavailable",
             "never follow a symlinked preference file")
try FileManager.default.removeItem(at: fixture)
precondition(panel.protectionProfileDetailsLabel.frame.minY > panel.destinationBrowserLabel.frame.maxY)
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.cancelButton }) == true)
precondition(panel.enhancedFindingsLabel.isHidden)
precondition(panel.enhancedFindingsDetailsButton.isHidden)
precondition(panel.enhancedFindingsDetailsButton.title == "Show technical details")
precondition(panel.enhancedFindingsDetailsButton.accessibilityIdentifier() == "enhancedFindingsDetailsToggle")
precondition(panel.enhancedFindingsScrollView.isHidden)
precondition(panel.contentView?.frame.height == 458)
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.enhancedFindingsDetailsButton }) == true)
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.enhancedFindingsScrollView }) == true)
let findingReport: [String: Any] = [
    "schemaVersion": 2, "authorizesOpen": false, "requiresBlock": true,
    "stageResults": [
        [
            "stage": "embeddedUrls", "outcome": "completed",
            "findings": [
                [
                    "code": "suspiciousUrl", "severity": "suspicious",
                    "objectNumber": 12, "pageNumber": NSNull(),
                    "result": [
                        "outcome": "reviewRequired",
                        "nextAction": "requestReviewBeforeOpening",
                        "explanation": "https://sensitive.invalid/never-display",
                        "malwareAssessment": "notConfirmed",
                    ],
                ],
                [
                    "code": "incrementalRevision", "severity": "blocking",
                    "objectNumber": NSNull(), "pageNumber": NSNull(),
                    "result": [
                        "outcome": "blocking",
                        "nextAction": "stopOpening",
                        "explanation": "This finding must stop opening.",
                    ],
                ],
            ],
        ],
        ["stage": "javascriptActions", "outcome": "notRun", "findings": []],
    ],
]
let findingData = try JSONSerialization.data(withJSONObject: findingReport)
panel.updateEnhancedFindings(from: findingData)
precondition(panel.contentView?.frame.height == 500)
precondition(!panel.enhancedFindingsLabel.isHidden)
precondition(!panel.enhancedFindingsDetailsButton.isHidden)
precondition(panel.enhancedFindingsDetailsButton.title == "Show technical details")
precondition(panel.enhancedFindingsDetailsButton.accessibilityLabel() == "Show technical details")
precondition(panel.enhancedFindingsScrollView.isHidden)
precondition(panel.enhancedFindingsLabel.stringValue.contains("Enhanced findings: 2"))
precondition(panel.enhancedFindingsLabel.stringValue.contains("incomplete stages: 1"))
precondition(panel.enhancedFindingsLabel.accessibilityIdentifier() == "enhancedFindingsSummary")
precondition(panel.enhancedFindingsTextView.accessibilityIdentifier() == "enhancedFindingsDetails")
precondition(panel.enhancedFindingsTextView.string.contains("Embedded URLs"))
precondition(panel.enhancedFindingsTextView.string.contains("Suspicious URL"))
precondition(panel.enhancedFindingsTextView.string.contains("Review required"))
precondition(panel.enhancedFindingsTextView.string.contains("Blocking"))
precondition(panel.enhancedFindingsTextView.string.contains("Opening stopped"))
precondition(panel.enhancedFindingsTextView.string.contains("Malware not confirmed"))
precondition(panel.enhancedFindingsTextView.string.contains("JavaScript actions: inspection not run"))
precondition(!panel.enhancedFindingsTextView.string.contains("sensitive.invalid"))
panel.enhancedFindingsDetailsButton.performClick(nil)
precondition(panel.contentView?.frame.height == 650)
precondition(panel.enhancedFindingsDetailsButton.title == "Hide technical details")
precondition(!panel.enhancedFindingsScrollView.isHidden)
precondition(panel.enhancedFindingsScrollView.frame.maxY < panel.enhancedFindingsDetailsButton.frame.minY)
precondition(panel.enhancedFindingsLabel.frame.minY > panel.enhancedFindingsDetailsButton.frame.maxY)
panel.enhancedFindingsDetailsButton.performClick(nil)
precondition(panel.contentView?.frame.height == 500)
precondition(panel.enhancedFindingsDetailsButton.title == "Show technical details")
precondition(panel.enhancedFindingsScrollView.isHidden)
precondition(panel.protectionProfileLabel.stringValue == "Active protection profile: Built-in")
precondition(panel.cancelButton.title == "Cancel")
let knownMaliciousReport: [String: Any] = [
    "schemaVersion": 2, "authorizesOpen": false, "requiresBlock": true,
    "stageResults": [[
        "stage": "executableContent", "outcome": "completed",
        "findings": [[
            "code": "knownMaliciousContent", "severity": "informational",
            "objectNumber": 23, "pageNumber": NSNull(),
            "result": [
                "outcome": "blocking", "nextAction": "stopOpening",
                "explanation": "Known malicious content was identified; opening is blocked.",
            ],
        ]],
    ]],
]
panel.updateEnhancedFindings(from: try JSONSerialization.data(withJSONObject: knownMaliciousReport))
precondition(panel.enhancedFindingsLabel.stringValue.contains("Enhanced findings: 1"))
precondition(panel.enhancedFindingsTextView.string.contains("Known malicious content"))
precondition(panel.enhancedFindingsTextView.string.contains("Opening stopped"))
var downgradedMaliciousReport = knownMaliciousReport
var maliciousStages = downgradedMaliciousReport["stageResults"] as! [[String: Any]]
var maliciousStage = maliciousStages[0]
var maliciousFindings = maliciousStage["findings"] as! [[String: Any]]
maliciousFindings[0]["result"] = [
    "outcome": "recorded", "nextAction": "continueRequiredChecks",
    "explanation": "No risk",
]
maliciousStage["findings"] = maliciousFindings
maliciousStages[0] = maliciousStage
downgradedMaliciousReport["stageResults"] = maliciousStages
downgradedMaliciousReport["requiresBlock"] = false
panel.updateEnhancedFindings(from: try JSONSerialization.data(withJSONObject: downgradedMaliciousReport))
precondition(panel.enhancedFindingsLabel.stringValue == "Enhanced findings unavailable")
precondition(!panel.enhancedFindingsTextView.string.contains("No risk"))
var badReport = findingReport
badReport["stageResults"] = [[
    "stage": "embeddedUrls", "outcome": "completed",
    "findings": [[
        "code": "suspiciousUrl", "severity": "critical",
        "result": ["outcome": "recorded", "nextAction": "continueRequiredChecks",
                   "explanation": "SECRET /Users/private/input.pdf"],
    ]],
]]
panel.updateEnhancedFindings(from: try JSONSerialization.data(withJSONObject: badReport))
precondition(panel.enhancedFindingsLabel.stringValue == "Enhanced findings unavailable")
precondition(panel.contentView?.frame.height == 500)
precondition(panel.enhancedFindingsDetailsButton.title == "Show technical details")
precondition(panel.enhancedFindingsScrollView.isHidden)
precondition(panel.enhancedFindingsTextView.string.contains("could not be verified"))
precondition(!panel.enhancedFindingsTextView.string.contains("SECRET"))
let invalidAssessmentReport: [String: Any] = [
    "schemaVersion": 2, "authorizesOpen": false, "requiresBlock": true,
    "stageResults": [[
        "stage": "embeddedUrls", "outcome": "completed",
        "findings": [[
            "code": "suspiciousUrl", "severity": "suspicious",
            "result": [
                "outcome": "reviewRequired",
                "nextAction": "requestReviewBeforeOpening",
                "explanation": "Fixed explanation only",
                "malwareAssessment": "confirmed",
            ],
        ]],
    ]],
]
panel.updateEnhancedFindings(from: try JSONSerialization.data(withJSONObject: invalidAssessmentReport))
precondition(panel.enhancedFindingsLabel.stringValue == "Enhanced findings unavailable")
precondition(!panel.enhancedFindingsTextView.string.contains("confirmed"))
panel.updateEnhancedFindings(from: Data(repeating: 65, count: 256 * 1024 + 1))
precondition(panel.enhancedFindingsLabel.stringValue == "Enhanced findings unavailable")
let emptyReport: [String: Any] = [
    "schemaVersion": 2, "authorizesOpen": false, "requiresBlock": false,
    "stageResults": [["stage": "annotations", "outcome": "completed", "findings": []]],
]
panel.updateEnhancedFindings(from: try JSONSerialization.data(withJSONObject: emptyReport))
precondition(panel.enhancedFindingsLabel.stringValue.contains("Enhanced findings: 0"))
precondition(panel.contentView?.frame.height == 500)
precondition(panel.enhancedFindingsDetailsButton.title == "Show technical details")
precondition(panel.enhancedFindingsScrollView.isHidden)
precondition(panel.enhancedFindingsTextView.string.contains("not a clean verdict"))
panel.updateEnhancedFindings(from: nil)
precondition(panel.enhancedFindingsLabel.isHidden)
precondition(panel.enhancedFindingsDetailsButton.isHidden)
precondition(panel.enhancedFindingsScrollView.isHidden)
precondition(panel.enhancedFindingsTextView.string.isEmpty)
precondition(panel.contentView?.frame.height == 458)
precondition(panel.progressIndicator.isIndeterminate)

let sanitizerFailure: [String: Any] = [
    "status": "sanitizerFailure",
    "kind": "sanitizerCrashed",
    "message": "The PDF sanitizer crashed; conversion stopped. This is not a malware detection.",
    "scanVerdict": "notAssessed",
    "permitsOpen": false,
]
let sanitizerData = try JSONSerialization.data(withJSONObject: sanitizerFailure)
precondition(MaximumSanitizationFailureSnapshot.decode(sanitizerData) != nil)
panel.updateMaximumSanitizationFailure(from: sanitizerData)
precondition(!panel.maximumSanitizationFailureLabel.isHidden)
precondition(panel.maximumSanitizationFailureLabel.accessibilityIdentifier() == "maximumSanitizationFailure")
precondition(panel.maximumSanitizationFailureLabel.stringValue.contains("sanitizer crashed"))
precondition(panel.maximumSanitizationFailureLabel.stringValue.contains("not assessed"))
precondition(panel.maximumSanitizationFailureLabel.accessibilityLabel() == panel.maximumSanitizationFailureLabel.stringValue)
precondition(panel.stageLabel.stringValue == "Attention required — opening stopped")
precondition(panel.cancelButton.title == "Close")
precondition(panel.progressIndicator.isHidden)
precondition(panel.contentView?.frame.height == 568)
panel.updateEnhancedFindings(from: findingData)
precondition(panel.contentView?.frame.height == 610)
precondition(panel.maximumSanitizationFailureLabel.frame.minY >= panel.enhancedFindingsLabel.frame.maxY)
panel.enhancedFindingsDetailsButton.performClick(nil)
precondition(panel.contentView?.frame.height == 760)
precondition(panel.maximumSanitizationFailureLabel.frame.minY > panel.enhancedFindingsLabel.frame.maxY)
panel.updateEnhancedFindings(from: nil)
precondition(panel.contentView?.frame.height == 568)
for unsafe in [
    sanitizerFailure.merging(["message": "/private/secret.pdf: malware FOUND"]) { _, new in new },
    sanitizerFailure.merging(["kind": "unknown"]) { _, new in new },
    sanitizerFailure.merging(["scanVerdict": "malwareDetected"]) { _, new in new },
    sanitizerFailure.merging(["permitsOpen": true]) { _, new in new },
    sanitizerFailure.merging(["extra": "secret"]) { _, new in new },
] {
    let data = try JSONSerialization.data(withJSONObject: unsafe)
    precondition(MaximumSanitizationFailureSnapshot.decode(data) == nil)
    panel.updateMaximumSanitizationFailure(from: data)
    precondition(panel.maximumSanitizationFailureLabel.stringValue.contains("could not be verified"))
    precondition(!panel.maximumSanitizationFailureLabel.stringValue.contains("/private"))
    precondition(!panel.maximumSanitizationFailureLabel.stringValue.contains("malware FOUND"))
    precondition(panel.cancelButton.title == "Close")
}
panel.updateMaximumSanitizationFailure(from: Data(repeating: 65, count: 4097))
precondition(panel.maximumSanitizationFailureLabel.stringValue.contains("could not be verified"))
panel.updateMaximumSanitizationFailure(from: nil)
precondition(panel.maximumSanitizationFailureLabel.isHidden)
precondition(panel.maximumSanitizationFailureLabel.stringValue.isEmpty)
precondition(panel.contentView?.frame.height == 458)
panel.showAttentionRequired(documentDescription: "blocked.pdf")
precondition(panel.isVisible)
precondition(panel.stageLabel.stringValue == "Attention required — opening stopped")
precondition(panel.filenameLabel.stringValue == "blocked.pdf")
precondition(panel.queuedDocumentCountLabel.stringValue == "0 documents queued")
precondition(panel.progressIndicator.isHidden)
precondition(panel.cancelButton.title == "Close")
panel.show(documentDescription: "another.pdf", stage: .scanning, activeScans: 1)
precondition(panel.cancelButton.title == "Cancel")
precondition(!panel.progressIndicator.isHidden)
panel.showAttentionRequired(documentDescription: "blocked.pdf")
panel.cancelButton.performClick(nil)
precondition(owner.pressed, "The caller owns cancellation")
panel.orderOut(nil)
print("PASS: one shared native progress panel, stage transitions, animation and caller-owned Cancel")
""")
            binary = root / "progress"
            subprocess.run(["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                            str(harness), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
