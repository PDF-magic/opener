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
        precondition(first.subviews.count == 1, "the component must own its layout")

        precondition(first.copyDiagnosticDetailsButton.title == "Copy Diagnostic Details")
        precondition(first.copyDiagnosticDetailsButton.accessibilityIdentifier()
                     == "scanResultSummaryCopyDiagnostics")
        precondition(first.copyDiagnosticDetailsButton.accessibilityLabel()
                     == "Copy Diagnostic Details")
        precondition(first.copyDiagnosticDetailsButton.action != nil)
        precondition(first.diagnosticDetailsForCopy().contains("Status: unavailable"))
        precondition(first.diagnosticDetailsForCopy().contains("Document path: Not provided"))

        let expected = [
            "clean", "malwareDetected", "suspiciousStructure", "encrypted",
            "incompleteScan", "scanFailed", "scanTimedOut", "fileChanged",
            "fileTooLarge", "cancelled",
        ]
        precondition(ScanResultSummaryStatus.allCases.map(\.rawValue) == expected)
        for status in ScanResultSummaryStatus.allCases {
            first.show(status)
            precondition(first.displayedStatus == status)
            precondition(first.diagnosticDetailsForCopy().contains("Status: " + status.rawValue))
            precondition(!first.diagnosticDetailsForCopy().contains("[redacted]"))
            precondition(first.displayedSanitization == nil)
            precondition(first.sanitizationLabel.stringValue == "Sanitization: Unavailable")
            precondition(!first.headingLabel.stringValue.isEmpty)
            precondition(!first.explanationLabel.stringValue.isEmpty)
            precondition(first.headingLabel.accessibilityLabel() == first.headingLabel.stringValue)
            precondition(first.explanationLabel.accessibilityLabel() == first.explanationLabel.stringValue)
            precondition(!first.explanationLabel.stringValue.contains("/Users/"))
            precondition(!first.explanationLabel.stringValue.contains("secret.pdf"))
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
        let safeCopy = first.diagnosticDetailsForCopy()
        precondition(safeCopy.contains("Status: clean"))
        precondition(safeCopy.contains("Document: März résumé 🦄.pdf"))
        precondition(safeCopy.contains("Document path: [redacted]"))
        precondition(safeCopy.contains("Selected protection level: Built-in"))
        precondition(safeCopy.contains("Sanitization: Performed"))
        precondition(safeCopy.contains("File integrity and verified opening checks still apply"))
        precondition(!safeCopy.contains("/Users/"))
        precondition(!safeCopy.contains("Private scans"))
        precondition(!safeCopy.contains(target.path))
        first.copyDiagnosticDetailsButton.performClick(nil)
        precondition(NSPasteboard.general.string(forType: .string) == safeCopy,
                     "button must copy only the privacy-safe snapshot")
        precondition(first.headingLabel.stringValue == "Scan complete")
        precondition(first.explanationLabel.stringValue.contains("still apply"))
        second.show(.scanFailed, documentURL: URL(fileURLWithPath: "/tmp/other.pdf"),
                    selectedProtectionLevel: .enhanced, sanitization: .notPerformed)
        precondition(second.displayedSanitization == .notPerformed)
        precondition(second.sanitizationLabel.stringValue == "Sanitization: Not performed")
        precondition(second.sanitizationLabel.accessibilityLabel()
                     == "Sanitization: Not performed")
        precondition(second.headingLabel.stringValue == "Scan failed")
        precondition(second.documentNameLabel.stringValue == "Document: other.pdf")
        precondition(second.diagnosticDetailsForCopy().contains("Status: scanFailed"))
        precondition(second.diagnosticDetailsForCopy().contains("Sanitization: Not performed"))
        precondition(second.diagnosticDetailsForCopy().contains("Document path: [redacted]"))
        precondition(!second.diagnosticDetailsForCopy().contains("/tmp/other.pdf"))
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
        precondition(ScanResultSummaryProtectionLevel(rawValue: "disabled") == nil)
        precondition(ScanResultSummaryProtectionLevel(rawValue: "custom") == nil)
        first.show(.fileChanged, documentURL: URL(string: "https://example.invalid/secret.pdf"),
                   selectedProtectionLevel: nil)
        precondition(first.documentNameLabel.stringValue == "Document: Unavailable")
        precondition(first.selectedProtectionLevelLabel.stringValue
                     == "Selected protection level: Unavailable")
        precondition(first.diagnosticDetailsForCopy().contains("Document path: Not provided"))

        precondition(!first.diagnosticDetailsForCopy().contains("example.invalid"))
        for unsafe in [
            "/tmp/line\nspoof.pdf",
            "/tmp/\u{202E}fdp.dab.pdf",
            "/tmp/" + String(repeating: "a", count: 260) + ".pdf"
        ] {
            first.show(.scanFailed, documentURL: URL(fileURLWithPath: unsafe),
                       selectedProtectionLevel: .builtIn)
            precondition(first.documentNameLabel.stringValue == "Document: Unavailable")
            let redacted = first.diagnosticDetailsForCopy()
            precondition(redacted.contains("Document: Unavailable"))
            precondition(redacted.contains("Document path: [redacted]"))
            precondition(!redacted.contains(unsafe))
            precondition(!redacted.contains("spoof.pdf"))
            precondition(!redacted.contains("fdp.dab.pdf"))
        }
        first.reset()
        precondition(first.displayedStatus == nil)
        precondition(first.diagnosticDetailsForCopy().contains("Status: unavailable"))
        precondition(first.diagnosticDetailsForCopy().contains("Document path: Not provided"))
        precondition(first.diagnosticDetailsForCopy().contains("Sanitization: Unavailable"))
        precondition(!first.diagnosticDetailsForCopy().contains("März résumé"))
        first.copyDiagnosticDetailsButton.performClick(nil)
        precondition(NSPasteboard.general.string(forType: .string)
                     == first.diagnosticDetailsForCopy())
        precondition(first.displayedProtectionLevel == nil)
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
