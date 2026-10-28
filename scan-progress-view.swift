import AppKit

// Shared native scan-progress presentation for the PDF opener and any later
// native entry point. This component never starts scans or changes scan policy.
// Render bundled reading artwork locally, with orbiting magic sparkles.
final class TwilightReadingView: NSView {
    private var timer: Timer?
    private let started = Date()
    private let artwork: NSImage? = {
        let source = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let url = Bundle.main.url(forResource: "twilight-reading", withExtension: "png")
            ?? source.appendingPathComponent("twilight-reading.png")
        return NSImage(contentsOf: url)
    }()

    override func viewDidMoveToWindow() {
        timer?.invalidate()
        if window != nil {
            timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 24, repeats: true) { [weak self] _ in
                self?.needsDisplay = true
            }
        }
    }

    deinit { timer?.invalidate() }

    override func draw(_ dirtyRect: NSRect) {
        let phase = Date().timeIntervalSince(started)
        let bob = sin(phase * 2) * 2
        let pink = NSColor(calibratedRed: 0.94, green: 0.25, blue: 0.64, alpha: 1)
        func line(_ points: [NSPoint], _ color: NSColor, _ width: CGFloat = 2) {
            let path = NSBezierPath()
            path.move(to: points[0])
            for point in points.dropFirst() { path.line(to: point) }
            color.setStroke(); path.lineWidth = width; path.lineCapStyle = .round; path.stroke()
        }
        if let artwork = artwork, artwork.size.width > 0, artwork.size.height > 0 {
            let scale = min(280 / artwork.size.width, 145 / artwork.size.height)
            let size = NSSize(width: artwork.size.width * scale, height: artwork.size.height * scale)
            artwork.draw(in: NSRect(x: (bounds.width - size.width) / 2,
                                    y: 109 - size.height / 2 + bob,
                                    width: size.width, height: size.height))
        }
        for index in 0..<7 {
            let angle = phase * 0.8 + Double(index) * .pi * 2 / 7
            let x = 151 + cos(angle) * 105
            let y = 109 + sin(angle) * 72
            let size = 3 + sin(phase * 3 + Double(index)) * 1.5
            line([NSPoint(x: x - size, y: y), NSPoint(x: x + size, y: y)], pink, 1.5)
            line([NSPoint(x: x, y: y - size), NSPoint(x: x, y: y + size)], pink, 1.5)
        }
    }
}

// These stages describe the native owner's observable process lifecycle, not
// ClamAV internals or a prediction that a document will be approved.
enum ScanProgressStage {
    case queued
    case starting
    case scanning

    var label: String {
        switch self {
        case .queued: return "Waiting to scan…"
        case .starting: return "Starting safety checks…"
        case .scanning: return "Scanning and verifying document…"
        }
    }
}

// The installed scan gate has one built-in, mandatory protection policy.
// This is a display descriptor, NOT a selectable or health-verified profile:
// a missing or failed scanner still blocks opening via the existing scan gate.
private enum BuiltInProtectionProfile {
    static let name = "Built-in"
    static let details = "ClamAV malware scanning · fail-closed"
}

final class ScanProgressPanel: NSPanel {
    let filenameLabel = NSTextField(labelWithString: "")
    let activeScansLabel = NSTextField(labelWithString: "Active scans: 0")
    let queuedDocumentCountLabel = NSTextField(labelWithString: "0 documents queued")
    let protectionProfileLabel = NSTextField(
        labelWithString: "Active protection profile: " + BuiltInProtectionProfile.name)
    let protectionProfileDetailsLabel = NSTextField(
        labelWithString: BuiltInProtectionProfile.details)
    let stageLabel = NSTextField(labelWithString: ScanProgressStage.queued.label)
    let progressIndicator = NSProgressIndicator(frame: NSRect(x: 30, y: 51, width: 300, height: 5))
    let cancelButton: NSButton

    init(cancelTarget: AnyObject, cancelAction: Selector) {
        cancelButton = NSButton(title: "Cancel", target: cancelTarget, action: cancelAction)
        super.init(contentRect: NSRect(x: 0, y: 0, width: 360, height: 432),
                   styleMask: [.titled], backing: .buffered, defer: false)
        title = "PDF Magic Opener — Scanning"
        level = .floating
        hidesOnDeactivate = false
        collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        isReleasedWhenClosed = false
        contentView?.addSubview(TwilightReadingView(
            frame: NSRect(x: 30, y: 212, width: 300, height: 205)))
        stageLabel.font = .systemFont(ofSize: 15, weight: .semibold)
        stageLabel.alignment = .center
        stageLabel.frame = NSRect(x: 20, y: 187, width: 320, height: 22)
        stageLabel.setAccessibilityLabel("Current scanning stage")
        contentView?.addSubview(stageLabel)
        filenameLabel.alignment = .center
        filenameLabel.lineBreakMode = .byTruncatingMiddle
        filenameLabel.textColor = .secondaryLabelColor
        filenameLabel.frame = NSRect(x: 20, y: 161, width: 320, height: 20)
        contentView?.addSubview(filenameLabel)
        activeScansLabel.alignment = .center
        activeScansLabel.font = .systemFont(ofSize: 12, weight: .semibold)
        activeScansLabel.textColor = .secondaryLabelColor
        activeScansLabel.frame = NSRect(x: 20, y: 135, width: 320, height: 20)
        activeScansLabel.setAccessibilityIdentifier("activeScanCount")
        activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)
        contentView?.addSubview(activeScansLabel)
        queuedDocumentCountLabel.alignment = .center
        queuedDocumentCountLabel.font = .systemFont(ofSize: 12)
        queuedDocumentCountLabel.textColor = .secondaryLabelColor
        queuedDocumentCountLabel.frame = NSRect(x: 20, y: 111, width: 320, height: 20)
        queuedDocumentCountLabel.setAccessibilityIdentifier("queuedDocumentCount")
        queuedDocumentCountLabel.setAccessibilityLabel(queuedDocumentCountLabel.stringValue)
        contentView?.addSubview(queuedDocumentCountLabel)
        protectionProfileLabel.alignment = .center
        protectionProfileLabel.font = .systemFont(ofSize: 12, weight: .medium)
        protectionProfileLabel.textColor = .secondaryLabelColor
        protectionProfileLabel.frame = NSRect(x: 20, y: 85, width: 320, height: 20)
        protectionProfileLabel.setAccessibilityLabel(protectionProfileLabel.stringValue)
        contentView?.addSubview(protectionProfileLabel)
        protectionProfileDetailsLabel.alignment = .center
        protectionProfileDetailsLabel.font = .systemFont(ofSize: 11)
        protectionProfileDetailsLabel.textColor = .secondaryLabelColor
        protectionProfileDetailsLabel.frame = NSRect(x: 20, y: 65, width: 320, height: 18)
        contentView?.addSubview(protectionProfileDetailsLabel)
        progressIndicator.style = .bar
        progressIndicator.isIndeterminate = true
        progressIndicator.startAnimation(nil)
        contentView?.addSubview(progressIndicator)
        cancelButton.bezelStyle = .rounded
        cancelButton.frame = NSRect(x: 136, y: 8, width: 88, height: 28)
        contentView?.addSubview(cancelButton)
        center()
    }

    // Set only display state. Callers own the scan lifecycle and Cancel action.
    func show(documentDescription: String, stage: ScanProgressStage = .queued,
              queuedDocumentCount: Int = 0, activeScans: Int = 0) {
        filenameLabel.stringValue = documentDescription
        stageLabel.stringValue = stage.label
        // Count only processes confirmed launched by the native owner, never
        // queued documents, scheduled workers, or duplicate open events.
        let count = max(0, activeScans)
        activeScansLabel.stringValue = "Active scans: \(count)"
        activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)
        // Only waiting documents are counted; active scans are displayed above.
        let waiting = max(0, queuedDocumentCount)
        let waitingText = "\(waiting) \(waiting == 1 ? "document" : "documents") queued"
        queuedDocumentCountLabel.stringValue = waitingText
        queuedDocumentCountLabel.setAccessibilityLabel(waitingText)
        orderFrontRegardless()
    }
}
