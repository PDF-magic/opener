import AppKit

// Reusable, presentation-only result summary for native scan-related UIs.
// Callers must supply a status from a trusted scan coordinator. This view
// never interprets PDF content, verifies a scan, or grants opening permission.
enum ScanResultSummaryStatus: String, CaseIterable {
    case clean
    case malwareDetected
    case suspiciousStructure
    case encrypted
    case incompleteScan
    case scanFailed
    case scanTimedOut
    case fileChanged
    case fileTooLarge
    case cancelled
}

private struct ScanResultSummaryCopy {
    let heading: String
    let explanation: String

    static func forStatus(_ status: ScanResultSummaryStatus?) -> ScanResultSummaryCopy {
        switch status {
        case .clean:
            return ScanResultSummaryCopy(
                heading: "Scan complete",
                explanation: "Required scanning reported no threats. File integrity and verified opening checks still apply.")
        case .malwareDetected:
            return ScanResultSummaryCopy(
                heading: "Malware detected",
                explanation: "The scanner reported a malware detection. Opening was stopped.")
        case .suspiciousStructure:
            return ScanResultSummaryCopy(
                heading: "Suspicious PDF structure",
                explanation: "Required structural checks identified suspicious content. Opening was stopped.")
        case .encrypted:
            return ScanResultSummaryCopy(
                heading: "Encrypted PDF",
                explanation: "Required inspection could not verify this encrypted document. Opening was stopped.")
        case .incompleteScan:
            return ScanResultSummaryCopy(
                heading: "Scan incomplete",
                explanation: "One or more required checks did not complete. Opening was stopped.")
        case .scanFailed:
            return ScanResultSummaryCopy(
                heading: "Scan failed",
                explanation: "The scanner could not verify the document. Opening was stopped.")
        case .scanTimedOut:
            return ScanResultSummaryCopy(
                heading: "Scan timed out",
                explanation: "Scanning exceeded the allowed time. Opening was stopped.")
        case .fileChanged:
            return ScanResultSummaryCopy(
                heading: "File changed",
                explanation: "The document changed during verification. Opening was stopped.")
        case .fileTooLarge:
            return ScanResultSummaryCopy(
                heading: "File exceeds scan limits",
                explanation: "A required size limit prevented complete scanning. Opening was stopped.")
        case .cancelled:
            return ScanResultSummaryCopy(
                heading: "Scan cancelled",
                explanation: "The scan request was cancelled. Opening was not authorized.")
        case nil:
            return ScanResultSummaryCopy(
                heading: "No verified scan result",
                explanation: "A trusted completed scan result is unavailable. Opening is not authorized.")
        }
    }
}

// This is an AppKit view, not a scanner control or a notification source.
// Multiple callers can embed separate instances and update them independently.
final class ScanResultSummaryView: NSView {
    let headingLabel = NSTextField(labelWithString: "")
    let explanationLabel = NSTextField(wrappingLabelWithString: "")
    private(set) var displayedStatus: ScanResultSummaryStatus?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        configure()
        reset()
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        configure()
        reset()
    }

    private func configure() {
        setAccessibilityIdentifier("scanResultSummary")
        setAccessibilityRole(.group)
        headingLabel.font = .systemFont(ofSize: 15, weight: .semibold)
        headingLabel.setAccessibilityIdentifier("scanResultSummaryHeading")
        explanationLabel.font = .systemFont(ofSize: 12)
        explanationLabel.textColor = .secondaryLabelColor
        explanationLabel.lineBreakMode = .byWordWrapping
        explanationLabel.maximumNumberOfLines = 0
        explanationLabel.setAccessibilityIdentifier("scanResultSummaryExplanation")

        let stack = NSStackView(views: [headingLabel, explanationLabel])
        stack.orientation = .vertical
        stack.alignment = .leading
        stack.spacing = 5
        stack.translatesAutoresizingMaskIntoConstraints = false
        addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            stack.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -12),
            stack.topAnchor.constraint(equalTo: topAnchor, constant: 10),
            stack.bottomAnchor.constraint(lessThanOrEqualTo: bottomAnchor, constant: -10),
        ])
        explanationLabel.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    }

    // An absence of a trusted terminal status must clear any earlier success.
    // The fixed display vocabulary never includes document paths, scanner
    // stderr, untrusted explanations, or a claim of authorization to open.
    func show(_ status: ScanResultSummaryStatus?) {
        displayedStatus = status
        let copy = ScanResultSummaryCopy.forStatus(status)
        headingLabel.stringValue = copy.heading
        explanationLabel.stringValue = copy.explanation
        headingLabel.setAccessibilityLabel(copy.heading)
        explanationLabel.setAccessibilityLabel(copy.explanation)
        switch status {
        case .clean:
            headingLabel.textColor = .systemGreen
        case .malwareDetected:
            headingLabel.textColor = .systemRed
        case .cancelled, nil:
            headingLabel.textColor = .labelColor
        default:
            headingLabel.textColor = .systemOrange
        }
    }

    func reset() {
        show(nil)
    }
}
