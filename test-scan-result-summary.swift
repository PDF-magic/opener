import AppKit

@main
struct ScanResultSummaryComponentTests {
    static func main() {
        let app = NSApplication.shared
        app.setActivationPolicy(.accessory)
        let first = ScanResultSummaryView(frame: NSRect(x: 0, y: 0, width: 420, height: 110))
        let second = ScanResultSummaryView(frame: NSRect(x: 0, y: 0, width: 420, height: 110))

        precondition(first.accessibilityIdentifier() == "scanResultSummary")
        precondition(first.displayedStatus == nil)
        precondition(first.headingLabel.stringValue == "No verified scan result")
        precondition(first.explanationLabel.stringValue.contains("not authorized"))
        precondition(first.headingLabel.accessibilityIdentifier() == "scanResultSummaryHeading")
        precondition(first.explanationLabel.accessibilityIdentifier() == "scanResultSummaryExplanation")
        precondition(first.documentNameLabel.accessibilityIdentifier() == "scanResultSummaryDocument")
        precondition(first.selectedProtectionLevelLabel.accessibilityIdentifier()
                     == "scanResultSummaryProtectionLevel")
        precondition(first.documentNameLabel.stringValue == "Document: Unavailable")
        precondition(first.selectedProtectionLevelLabel.stringValue
                     == "Selected protection level: Unavailable")
        precondition(first.sanitizationLabel.accessibilityIdentifier()
                     == "scanResultSummarySanitization")
        precondition(first.sanitizationLabel.stringValue == "Sanitization: Unavailable")
        precondition(first.sanitizationLabel.accessibilityLabel()
                     == "Sanitization: Unavailable")
        precondition(first.displayedSanitization == nil)
        precondition(first.fileOpenedLabel.accessibilityIdentifier() == "scanResultSummaryFileOpened")
        precondition(first.fileBlockedLabel.accessibilityIdentifier() == "scanResultSummaryFileBlocked")
        precondition(first.blockingReasonLabel.accessibilityIdentifier()
                     == "scanResultSummaryBlockingReason")
        precondition(first.fileOpenedLabel.stringValue == "File opened: Not confirmed")
        precondition(first.fileBlockedLabel.stringValue == "File blocked: Not confirmed")
        precondition(first.blockingReasonLabel.stringValue == "Blocking reason: Not confirmed")
        precondition(first.subviews.count == 1, "the component must own its layout")

        let expected = [
            "clean", "malwareDetected", "suspiciousStructure", "encrypted",
            "incompleteScan", "scanFailed", "scanTimedOut", "fileChanged",
            "fileTooLarge", "cancelled",
        ]
        precondition(ScanResultSummaryStatus.allCases.map(\.rawValue) == expected)
        for status in ScanResultSummaryStatus.allCases {
            first.show(status)
            precondition(first.displayedStatus == status)
            precondition(first.displayedSanitization == nil)
            precondition(first.sanitizationLabel.stringValue == "Sanitization: Unavailable")
            precondition(!first.headingLabel.stringValue.isEmpty)
            precondition(!first.explanationLabel.stringValue.isEmpty)
            precondition(first.headingLabel.accessibilityLabel() == first.headingLabel.stringValue)
            precondition(first.explanationLabel.accessibilityLabel() == first.explanationLabel.stringValue)
            precondition(!first.explanationLabel.stringValue.contains("/Users/"))
            precondition(!first.explanationLabel.stringValue.contains("secret.pdf"))
            precondition(first.fileOpenedLabel.accessibilityLabel()
                         == first.fileOpenedLabel.stringValue)
            precondition(first.fileBlockedLabel.accessibilityLabel()
                         == first.fileBlockedLabel.stringValue)
            precondition(first.blockingReasonLabel.accessibilityLabel()
                         == first.blockingReasonLabel.stringValue)
            if status == .clean {
                // Clean scanning is not evidence that the app launched.
                precondition(first.fileOpenedLabel.stringValue == "File opened: Not confirmed")
                precondition(first.fileBlockedLabel.stringValue == "File blocked: Not confirmed")
                precondition(first.blockingReasonLabel.stringValue
                             == "Blocking reason: Not confirmed")
            } else {
                precondition(first.fileOpenedLabel.stringValue == "File opened: No")
                precondition(first.fileBlockedLabel.stringValue == "File blocked: Yes")
                precondition(first.blockingReasonLabel.stringValue.hasPrefix("Blocking reason: "))
                precondition(first.blockingReasonLabel.stringValue != "Blocking reason: None")
                precondition(!first.blockingReasonLabel.stringValue.contains("/Users/"))
                precondition(!first.blockingReasonLabel.stringValue.contains("secret.pdf"))
            }
            if status != .clean {
                precondition(!first.headingLabel.stringValue.contains("Scan complete"))
                precondition(first.explanationLabel.stringValue.contains("Opening"))
            }
            if status != .malwareDetected {
                precondition(!first.headingLabel.stringValue.contains("Malware detected"))
            }
        }

        let target = URL(fileURLWithPath: "/Users/example/Private scans/März résumé 🦄.pdf")
        first.show(.clean, documentURL: target, selectedProtectionLevel: .builtIn,
                   sanitization: .performed)
        precondition(first.displayedSanitization == .performed)
        precondition(first.sanitizationLabel.stringValue == "Sanitization: Performed")
        precondition(first.sanitizationLabel.accessibilityLabel()
                     == "Sanitization: Performed")
        precondition(first.documentNameLabel.stringValue == "Document: März résumé 🦄.pdf")
        precondition(!first.documentNameLabel.stringValue.contains("/Users/"))
        precondition(first.documentNameLabel.accessibilityLabel()
                     == "Document: März résumé 🦄.pdf")
        precondition(first.selectedProtectionLevelLabel.stringValue
                     == "Selected protection level: Built-in")
        precondition(first.selectedProtectionLevelLabel.accessibilityLabel()
                     == "Selected protection level: Built-in")
        precondition(first.displayedProtectionLevel == .builtIn)
        precondition(first.headingLabel.stringValue == "Scan complete")
        precondition(first.explanationLabel.stringValue.contains("still apply"))
        // The trusted post-handoff signal is the only path to displaying opened.
        first.show(.clean, documentURL: target, selectedProtectionLevel: .builtIn,
                   openingOutcome: .opened)
        precondition(first.fileOpenedLabel.stringValue == "File opened: Yes")
        precondition(first.fileBlockedLabel.stringValue == "File blocked: No")
        precondition(first.blockingReasonLabel.stringValue == "Blocking reason: None")
        precondition(first.displayedOpeningOutcome == .opened)

        // An explicit post-scan opening denial must not be presented as success.
        first.show(.clean, documentURL: target, openingOutcome: .blocked)
        precondition(first.fileOpenedLabel.stringValue == "File opened: No")
        precondition(first.fileBlockedLabel.stringValue == "File blocked: Yes")
        precondition(first.blockingReasonLabel.stringValue
                     == "Blocking reason: Verified opening did not complete.")
        first.show(.clean, documentURL: target, selectedProtectionLevel: .builtIn,
                   openingOutcome: .opened)

        second.show(.scanFailed, documentURL: URL(fileURLWithPath: "/tmp/other.pdf"),
                    selectedProtectionLevel: .enhanced, sanitization: .notPerformed)
        precondition(second.displayedSanitization == .notPerformed)
        precondition(second.sanitizationLabel.stringValue == "Sanitization: Not performed")
        precondition(second.sanitizationLabel.accessibilityLabel()
                     == "Sanitization: Not performed")
        precondition(second.headingLabel.stringValue == "Scan failed")
        precondition(second.fileBlockedLabel.stringValue == "File blocked: Yes")
        precondition(second.blockingReasonLabel.stringValue
                     == "Blocking reason: Required scanning failed.")
        precondition(second.documentNameLabel.stringValue == "Document: other.pdf")
        precondition(second.selectedProtectionLevelLabel.stringValue.contains("Enhanced"))
        precondition(second.selectedProtectionLevelLabel.stringValue.contains("preview only"))
        precondition(second.selectedProtectionLevelLabel.stringValue.contains(
            "Built-in scanning remains active"))
        precondition(first.selectedProtectionLevelLabel.stringValue
                     == "Selected protection level: Built-in")
        precondition(first.headingLabel.stringValue == "Scan complete",
                     "separate instances must not share mutable presentation state")
        for (level, title) in [
            (ScanResultSummaryProtectionLevel.standard, "Standard"),
            (.enhanced, "Enhanced"),
            (.maximum, "Maximum")
        ] {
            first.show(.incompleteScan, documentURL: target, selectedProtectionLevel: level)
            precondition(first.displayedSanitization == nil)
            precondition(first.sanitizationLabel.stringValue == "Sanitization: Unavailable")
            precondition(first.selectedProtectionLevelLabel.stringValue.contains(title))
            precondition(first.selectedProtectionLevelLabel.stringValue.contains("preview only"))
            precondition(first.selectedProtectionLevelLabel.stringValue.contains(
                "Built-in scanning remains active"))
            precondition(first.headingLabel.stringValue != "Scan complete")
        }
        precondition(ScanResultSummarySanitization(rawValue: "attempted") == nil)
        precondition(ScanResultSummarySanitization(rawValue: "failed") == nil)
        // Neither a clean verdict nor a preview-only Maximum selection proves conversion.
        first.show(.clean, documentURL: target, selectedProtectionLevel: .maximum)
        precondition(first.sanitizationLabel.stringValue == "Sanitization: Unavailable")
        first.show(.malwareDetected, sanitization: .performed)
        precondition(first.sanitizationLabel.stringValue == "Sanitization: Performed")
        precondition(first.headingLabel.stringValue == "Malware detected")
        precondition(first.explanationLabel.stringValue.contains("Opening was stopped"))
        precondition(second.sanitizationLabel.stringValue == "Sanitization: Not performed")
        // Never trust a stale or contradictory opened signal for denied scans.
        first.show(.malwareDetected, documentURL: target, openingOutcome: .opened)
        precondition(first.fileOpenedLabel.stringValue == "File opened: No")
        precondition(first.fileBlockedLabel.stringValue == "File blocked: Yes")
        precondition(first.blockingReasonLabel.stringValue
                     == "Blocking reason: Malware was detected.")
        precondition(first.displayedOpeningOutcome == .blocked)
        first.show(nil, documentURL: target, openingOutcome: .opened)
        precondition(first.displayedOpeningOutcome == nil)
        precondition(first.fileOpenedLabel.stringValue == "File opened: Not confirmed")
        precondition(first.fileBlockedLabel.stringValue == "File blocked: Not confirmed")
        precondition(ScanResultSummaryProtectionLevel(rawValue: "disabled") == nil)
        precondition(ScanResultSummaryProtectionLevel(rawValue: "custom") == nil)
        first.show(.fileChanged, documentURL: URL(string: "https://example.invalid/secret.pdf"),
                   selectedProtectionLevel: nil)
        precondition(first.documentNameLabel.stringValue == "Document: Unavailable")
        precondition(first.selectedProtectionLevelLabel.stringValue
                     == "Selected protection level: Unavailable")
        for unsafe in [
            "/tmp/line\nspoof.pdf",
            "/tmp/\u{202E}fdp.dab.pdf",
            "/tmp/" + String(repeating: "a", count: 260) + ".pdf"
        ] {
            first.show(.scanFailed, documentURL: URL(fileURLWithPath: unsafe),
                       selectedProtectionLevel: .builtIn)
            precondition(first.documentNameLabel.stringValue == "Document: Unavailable")
        }
        first.reset()
        precondition(first.displayedStatus == nil)
        precondition(first.displayedProtectionLevel == nil)
        precondition(first.displayedOpeningOutcome == nil)
        precondition(first.fileOpenedLabel.stringValue == "File opened: Not confirmed")
        precondition(first.fileBlockedLabel.stringValue == "File blocked: Not confirmed")
        precondition(ScanResultSummaryProtectionLevel(rawValue: "disabled") == nil)
        precondition(ScanResultSummaryProtectionLevel(rawValue: "custom") == nil)
        first.show(.fileChanged, documentURL: URL(string: "https://example.invalid/secret.pdf"),
                   selectedProtectionLevel: nil)
        precondition(first.displayedSanitization == nil)
        precondition(first.sanitizationLabel.stringValue == "Sanitization: Unavailable")
        precondition(first.sanitizationLabel.accessibilityLabel()
                     == "Sanitization: Unavailable")
        precondition(first.documentNameLabel.stringValue == "Document: Unavailable")
        precondition(first.selectedProtectionLevelLabel.stringValue
                     == "Selected protection level: Unavailable")
        precondition(first.headingLabel.stringValue == "No verified scan result")
        precondition(first.explanationLabel.stringValue.contains("not authorized"),
                     "reset must not leave stale clean status visible")
        precondition(second.headingLabel.stringValue == "Scan failed")
        print("Reusable scan result summary component passed")
    }
}
