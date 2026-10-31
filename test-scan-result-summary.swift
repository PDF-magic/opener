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

        first.show(.clean)
        precondition(first.headingLabel.stringValue == "Scan complete")
        precondition(first.explanationLabel.stringValue.contains("still apply"))
        second.show(.scanFailed)
        precondition(second.headingLabel.stringValue == "Scan failed")
        precondition(first.headingLabel.stringValue == "Scan complete",
                     "separate instances must not share mutable presentation state")
        first.reset()
        precondition(first.displayedStatus == nil)
        precondition(first.headingLabel.stringValue == "No verified scan result")
        precondition(first.explanationLabel.stringValue.contains("not authorized"),
                     "reset must not leave stale clean status visible")
        precondition(second.headingLabel.stringValue == "Scan failed")
        print("Reusable scan result summary component passed")
    }
}
