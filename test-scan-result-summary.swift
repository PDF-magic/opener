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
        precondition(first.structureAnalysisLabel.accessibilityIdentifier()
                     == "scanResultSummaryStructureAnalysis")
        precondition(first.structureAnalysisLabel.stringValue == "Structure analysis: Unavailable")
        precondition(first.structureAnalysisLabel.accessibilityLabel()
                     == "Structure analysis: Unavailable")
        precondition(first.displayedStructureAnalysisCompleted == nil)
        precondition(first.technicalDetailsButton.accessibilityIdentifier()
                     == "scanResultSummaryTechnicalDetailsToggle")
        precondition(first.technicalDetailsLabel.accessibilityIdentifier()
                     == "scanResultSummaryTechnicalDetails")
        precondition(first.technicalDetailsButton.isHidden)
        precondition(first.technicalDetailsLabel.isHidden)
        precondition(first.technicalDetailsLabel.stringValue.isEmpty)
        precondition(!first.technicalDetailsExpanded)
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
            precondition(first.displayedStructureAnalysisCompleted == nil)
            precondition(first.structureAnalysisLabel.stringValue == "Structure analysis: Unavailable",
                         "a scanner verdict cannot establish structural completion")
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
            if status == .clean || status == .cancelled {
                precondition(first.technicalDetailsButton.isHidden)
                precondition(first.technicalDetailsLabel.isHidden)
                precondition(first.technicalDetailsLabel.stringValue.isEmpty)
            } else {
                precondition(!first.technicalDetailsButton.isHidden)
                precondition(first.technicalDetailsLabel.isHidden)
                precondition(!first.technicalDetailsExpanded)
                precondition(first.technicalDetailsButton.title == "Show technical details")
                precondition(first.technicalDetailsLabel.stringValue.contains(
                    "Result code: " + status.rawValue))
                precondition(first.technicalDetailsLabel.stringValue.contains(
                    "Opening was not authorized."))
                precondition(!first.technicalDetailsLabel.stringValue.contains("/Users/"))
                precondition(!first.technicalDetailsLabel.stringValue.contains("secret.pdf"))
                precondition(!first.technicalDetailsLabel.stringValue.contains("stderr"))
                first.technicalDetailsButton.performClick(nil)
                precondition(first.technicalDetailsExpanded)
                precondition(!first.technicalDetailsLabel.isHidden)
                precondition(first.technicalDetailsButton.title == "Hide technical details")
                precondition(first.technicalDetailsButton.accessibilityLabel()
                             == "Hide technical details")
                precondition(first.technicalDetailsLabel.accessibilityLabel()
                             == first.technicalDetailsLabel.stringValue)
                first.technicalDetailsButton.performClick(nil)
                precondition(!first.technicalDetailsExpanded)
                precondition(first.technicalDetailsLabel.isHidden)
                precondition(first.technicalDetailsButton.title == "Show technical details")
            }
        }

        let target = URL(fileURLWithPath: "/Users/example/Private scans/März résumé 🦄.pdf")
        first.show(.clean, documentURL: target, selectedProtectionLevel: .builtIn,
                   sanitization: .performed, structureAnalysisCompleted: true)
        precondition(first.displayedSanitization == .performed)
        precondition(first.displayedStructureAnalysisCompleted == true)
        precondition(first.structureAnalysisLabel.stringValue == "Structure analysis: Completed")
        precondition(first.structureAnalysisLabel.accessibilityLabel()
                     == "Structure analysis: Completed")
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
        second.show(.scanFailed, documentURL: URL(fileURLWithPath: "/tmp/other.pdf"),
                    selectedProtectionLevel: .enhanced, sanitization: .notPerformed,
                    structureAnalysisCompleted: false)
        precondition(second.displayedSanitization == .notPerformed)
        precondition(second.displayedStructureAnalysisCompleted == false)
        precondition(second.structureAnalysisLabel.stringValue == "Structure analysis: Not completed")
        precondition(second.structureAnalysisLabel.accessibilityLabel()
                     == "Structure analysis: Not completed")
        precondition(first.structureAnalysisLabel.stringValue == "Structure analysis: Completed",
                     "separate views must not share completion state")
        precondition(second.sanitizationLabel.stringValue == "Sanitization: Not performed")
        precondition(second.sanitizationLabel.accessibilityLabel()
                     == "Sanitization: Not performed")
        precondition(second.headingLabel.stringValue == "Scan failed")
        precondition(second.documentNameLabel.stringValue == "Document: other.pdf")
        precondition(second.selectedProtectionLevelLabel.stringValue.contains("Enhanced"))
        precondition(second.selectedProtectionLevelLabel.stringValue.contains("preview only"))
        precondition(second.selectedProtectionLevelLabel.stringValue.contains(
            "Built-in scanning remains active"))
        precondition(!second.technicalDetailsButton.isHidden)
        second.technicalDetailsButton.performClick(nil)
        precondition(second.technicalDetailsExpanded)
        precondition(second.technicalDetailsLabel.stringValue.contains("scanFailed"))
        precondition(first.technicalDetailsButton.isHidden)
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
        precondition(first.displayedStructureAnalysisCompleted == nil)
        precondition(first.structureAnalysisLabel.stringValue == "Structure analysis: Unavailable",
                     "new scan results without structural evidence must clear old completion")
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
        precondition(first.displayedStructureAnalysisCompleted == nil)
        precondition(first.structureAnalysisLabel.stringValue == "Structure analysis: Unavailable")
        precondition(first.structureAnalysisLabel.accessibilityLabel()
                     == "Structure analysis: Unavailable")
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
        precondition(first.technicalDetailsButton.isHidden)
        precondition(first.technicalDetailsLabel.isHidden)
        precondition(first.technicalDetailsLabel.stringValue.isEmpty)
        precondition(!first.technicalDetailsExpanded)
        precondition(second.technicalDetailsExpanded, "separate instances must retain state")
        precondition(second.structureAnalysisLabel.stringValue == "Structure analysis: Not completed")
        precondition(second.headingLabel.stringValue == "Scan failed")
        second.show(nil)
        precondition(second.technicalDetailsButton.isHidden)
        precondition(second.technicalDetailsLabel.stringValue.isEmpty)
        precondition(!second.technicalDetailsExpanded)
        precondition(second.structureAnalysisLabel.stringValue == "Structure analysis: Unavailable")
        print("Reusable scan result summary component passed")
    }
}
