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
        precondition(first.malwareStatusLabel.accessibilityIdentifier() == "scanResultSummaryMalware")
        precondition(first.malwareStatusLabel.stringValue == "Malware: Not determined")
        precondition(first.malwareStatusLabel.accessibilityLabel() == "Malware: Not determined")
        precondition(first.documentNameLabel.accessibilityIdentifier() == "scanResultSummaryDocument")
        precondition(first.selectedProtectionLevelLabel.accessibilityIdentifier()
                     == "scanResultSummaryProtectionLevel")
        precondition(first.documentNameLabel.stringValue == "Document: Unavailable")
        precondition(first.selectedProtectionLevelLabel.stringValue
                     == "Selected protection level: Unavailable")
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
            let expectedMalware = status == .malwareDetected ? "Malware: Detected"
                : status == .clean ? "Malware: Not detected" : "Malware: Not determined"
            precondition(first.malwareStatusLabel.stringValue == expectedMalware)
            precondition(first.malwareStatusLabel.accessibilityLabel() == expectedMalware)
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
        first.show(.clean, documentURL: target, selectedProtectionLevel: .builtIn)
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
        precondition(first.malwareStatusLabel.stringValue == "Malware: Not detected")
        precondition(first.explanationLabel.stringValue.contains("still apply"))
        second.show(.scanFailed, documentURL: URL(fileURLWithPath: "/tmp/other.pdf"),
                    selectedProtectionLevel: .enhanced)
        precondition(second.headingLabel.stringValue == "Scan failed")
        precondition(second.malwareStatusLabel.stringValue == "Malware: Not determined")
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
            precondition(first.selectedProtectionLevelLabel.stringValue.contains(title))
            precondition(first.selectedProtectionLevelLabel.stringValue.contains("preview only"))
            precondition(first.selectedProtectionLevelLabel.stringValue.contains(
                "Built-in scanning remains active"))
            precondition(first.headingLabel.stringValue != "Scan complete")
        }
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
        first.show(.malwareDetected, documentURL: target, selectedProtectionLevel: .builtIn)
        precondition(first.malwareStatusLabel.stringValue == "Malware: Detected")
        precondition(first.headingLabel.stringValue == "Malware detected")
        precondition(second.malwareStatusLabel.stringValue == "Malware: Not determined")
        first.reset()
        precondition(first.displayedStatus == nil)
        precondition(first.malwareStatusLabel.stringValue == "Malware: Not determined")
        precondition(first.displayedProtectionLevel == nil)
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
