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

// The user's selected presentation tier is separate from the enforced Built-in
// scanner. Planned profiles never activate unimplemented protection controls.
enum ScanResultSummaryProtectionLevel: String, CaseIterable {
    case builtIn = "built-in"
    case standard
    case enhanced
    case maximum

    var displayText: String {
        switch self {
        case .builtIn:
            return "Selected protection level: Built-in"
        case .standard:
            return "Selected protection level: Standard (preview only; Built-in scanning remains active)"
        case .enhanced:
            return "Selected protection level: Enhanced (preview only; Built-in scanning remains active)"
        case .maximum:
            return "Selected protection level: Maximum (preview only; Built-in scanning remains active)"
        }
    }
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
    let malwareStatusLabel = NSTextField(labelWithString: "Malware: Not determined")
    let documentNameLabel = NSTextField(labelWithString: "Document: Unavailable")
    let selectedProtectionLevelLabel = NSTextField(
        wrappingLabelWithString: "Selected protection level: Unavailable")
    private(set) var displayedStatus: ScanResultSummaryStatus?
    private(set) var displayedProtectionLevel: ScanResultSummaryProtectionLevel?

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
        malwareStatusLabel.font = .systemFont(ofSize: 12)
        malwareStatusLabel.textColor = .secondaryLabelColor
        malwareStatusLabel.setAccessibilityIdentifier("scanResultSummaryMalware")

        documentNameLabel.font = .systemFont(ofSize: 12)
        documentNameLabel.textColor = .secondaryLabelColor
        documentNameLabel.lineBreakMode = .byTruncatingMiddle
        documentNameLabel.setAccessibilityIdentifier("scanResultSummaryDocument")
        selectedProtectionLevelLabel.font = .systemFont(ofSize: 12)
        selectedProtectionLevelLabel.textColor = .secondaryLabelColor
        selectedProtectionLevelLabel.lineBreakMode = .byWordWrapping
        selectedProtectionLevelLabel.setAccessibilityIdentifier("scanResultSummaryProtectionLevel")

        let stack = NSStackView(views: [
            headingLabel, documentNameLabel, selectedProtectionLevelLabel,
            malwareStatusLabel, explanationLabel
        ])
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

    // Only a trusted local URL is accepted. Display its basename, never the
    // directory or raw path; control and bidi characters cannot spoof labels.
    private static func displayDocumentName(_ url: URL?) -> String {
        guard let url, url.isFileURL else { return "Unavailable" }
        let name = url.lastPathComponent
        let bidiControls: Set<UInt32> = [
            0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
            0x2066, 0x2067, 0x2068, 0x2069
        ]
        guard !name.isEmpty, name != ".", name != "..",
              name.utf8.count <= 255,
              !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !name.contains("/"), !name.contains("\\"),
              !name.unicodeScalars.contains(where: {
                  CharacterSet.controlCharacters.contains($0)
                      || bidiControls.contains($0.value)
              }) else {
            return "Unavailable"
        }
        return name
    }

    // Context comes from the trusted scan-request owner, never page contents
    // or extension messages. Unknown or absent selections stay unavailable.
    // A new request clears any prior name, tier or successful scan result.
    func show(
        _ status: ScanResultSummaryStatus?,
        documentURL: URL? = nil,
        selectedProtectionLevel: ScanResultSummaryProtectionLevel? = nil
    ) {
        displayedStatus = status
        displayedProtectionLevel = selectedProtectionLevel
        let document = "Document: " + Self.displayDocumentName(documentURL)
        documentNameLabel.stringValue = document
        documentNameLabel.setAccessibilityLabel(document)
        let protection = selectedProtectionLevel?.displayText
            ?? "Selected protection level: Unavailable"
        selectedProtectionLevelLabel.stringValue = protection
        selectedProtectionLevelLabel.setAccessibilityLabel(protection)
        // Only a verified clean terminal outcome supports a negative detection
        // statement. Every other unsuccessful or absent result is inconclusive.
        let malwareStatus: String
        switch status {
        case .malwareDetected:
            malwareStatus = "Malware: Detected"
        case .clean:
            malwareStatus = "Malware: Not detected"
        default:
            malwareStatus = "Malware: Not determined"
        }
        malwareStatusLabel.stringValue = malwareStatus
        malwareStatusLabel.setAccessibilityLabel(malwareStatus)
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
