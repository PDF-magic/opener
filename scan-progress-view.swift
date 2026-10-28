import AppKit
import Darwin

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

// Read-only presentation of the installed scanner's selected PDF destination.
// Mirror the verified chooser's target-app.txt contract; never use this label
// to select a launcher, authorize opening, or change the scanner's fail-closed gate.
enum SelectedDestinationBrowser {
    private static let names = [
        "com.brave.Browser": "Brave",
        "com.google.Chrome": "Google Chrome",
        "org.chromium.Chromium": "Chromium",
        "com.microsoft.edgemac": "Microsoft Edge",
        "com.vivaldi.Vivaldi": "Vivaldi",
        "com.operasoftware.Opera": "Opera",
        "company.thebrowser.Browser": "Arc",
        "org.mozilla.firefox": "Firefox",
        "com.apple.Safari": "Safari",
    ]

    static func displayName(
        in directory: URL = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Studio/allow-and-open",
                                    isDirectory: true)
    ) -> String {
        guard directory.isFileURL else { return "Unavailable" }
        let parent = open(directory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC)
        guard parent >= 0 else { return errno == ENOENT ? "Brave" : "Unavailable" }
        defer { close(parent) }

        let file = openat(parent, "target-app.txt", O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
        guard file >= 0 else { return errno == ENOENT ? "Brave" : "Unavailable" }
        defer { close(file) }

        var info = stat()
        guard fstat(file, &info) == 0,
              (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else {
            return "Unavailable"
        }
        var bytes = [UInt8](repeating: 0, count: 257)
        let count = read(file, &bytes, bytes.count)
        guard count > 0, count <= 256,
              let text = String(bytes: bytes.prefix(count), encoding: .ascii) else {
            return "Unavailable"
        }
        let identifier = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if identifier == "system-default-browser" { return "System default browser" }
        guard identifier.count <= 255,
              identifier.range(of: "^[A-Za-z0-9][A-Za-z0-9.-]{1,254}$",
                               options: .regularExpression) != nil,
              identifier.contains("."), !identifier.contains(".."),
              identifier != "local.studio.brave-pdf-opener" else {
            return "Unavailable"
        }
        return names[identifier] ?? "Custom application (\(identifier))"
    }
}

final class ScanProgressPanel: NSPanel {
    let filenameLabel = NSTextField(labelWithString: "")
    let destinationBrowserLabel = NSTextField(labelWithString: "Destination browser: Unavailable")
    let activeScansLabel = NSTextField(labelWithString: "Active scans: 0")
    let protectionProfileLabel = NSTextField(
        labelWithString: "Active protection profile: " + BuiltInProtectionProfile.name)
    let protectionProfileDetailsLabel = NSTextField(
        labelWithString: BuiltInProtectionProfile.details)
    let stageLabel = NSTextField(labelWithString: ScanProgressStage.queued.label)
    let progressIndicator = NSProgressIndicator(frame: NSRect(x: 30, y: 51, width: 300, height: 5))
    let cancelButton: NSButton

    init(cancelTarget: AnyObject, cancelAction: Selector) {
        cancelButton = NSButton(title: "Cancel", target: cancelTarget, action: cancelAction)
        super.init(contentRect: NSRect(x: 0, y: 0, width: 360, height: 434),
                   styleMask: [.titled], backing: .buffered, defer: false)
        title = "PDF Magic Opener — Scanning"
        level = .floating
        hidesOnDeactivate = false
        collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        isReleasedWhenClosed = false
        contentView?.addSubview(TwilightReadingView(
            frame: NSRect(x: 30, y: 214, width: 300, height: 205)))
        stageLabel.font = .systemFont(ofSize: 15, weight: .semibold)
        stageLabel.alignment = .center
        stageLabel.frame = NSRect(x: 20, y: 189, width: 320, height: 22)
        stageLabel.setAccessibilityLabel("Current scanning stage")
        contentView?.addSubview(stageLabel)
        filenameLabel.alignment = .center
        filenameLabel.lineBreakMode = .byTruncatingMiddle
        filenameLabel.textColor = .secondaryLabelColor
        filenameLabel.frame = NSRect(x: 20, y: 163, width: 320, height: 20)
        contentView?.addSubview(filenameLabel)
        activeScansLabel.alignment = .center
        activeScansLabel.font = .systemFont(ofSize: 12, weight: .semibold)
        activeScansLabel.textColor = .secondaryLabelColor
        activeScansLabel.frame = NSRect(x: 20, y: 137, width: 320, height: 20)
        activeScansLabel.setAccessibilityIdentifier("activeScanCount")
        activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)
        contentView?.addSubview(activeScansLabel)
        protectionProfileLabel.alignment = .center
        protectionProfileLabel.font = .systemFont(ofSize: 12, weight: .medium)
        protectionProfileLabel.textColor = .secondaryLabelColor
        protectionProfileLabel.frame = NSRect(x: 20, y: 111, width: 320, height: 20)
        protectionProfileLabel.setAccessibilityLabel(protectionProfileLabel.stringValue)
        contentView?.addSubview(protectionProfileLabel)
        protectionProfileDetailsLabel.alignment = .center
        protectionProfileDetailsLabel.font = .systemFont(ofSize: 11)
        protectionProfileDetailsLabel.textColor = .secondaryLabelColor
        protectionProfileDetailsLabel.frame = NSRect(x: 20, y: 91, width: 320, height: 18)
        contentView?.addSubview(protectionProfileDetailsLabel)
        destinationBrowserLabel.alignment = .center
        destinationBrowserLabel.font = .systemFont(ofSize: 12)
        destinationBrowserLabel.lineBreakMode = .byTruncatingMiddle
        destinationBrowserLabel.textColor = .secondaryLabelColor
        destinationBrowserLabel.frame = NSRect(x: 20, y: 67, width: 320, height: 20)
        destinationBrowserLabel.setAccessibilityLabel(destinationBrowserLabel.stringValue)
        contentView?.addSubview(destinationBrowserLabel)
        progressIndicator.style = .bar
        progressIndicator.isIndeterminate = true
        progressIndicator.startAnimation(nil)
        contentView?.addSubview(progressIndicator)
        cancelButton.bezelStyle = .rounded
        cancelButton.frame = NSRect(x: 136, y: 8, width: 88, height: 28)
        contentView?.addSubview(cancelButton)
        center()
    }

    // This is information only: the scan gate still chooses and validates
    // the actual application after a successful verdict.
    func updateDestinationBrowser(_ displayName: String) {
        destinationBrowserLabel.stringValue = "Destination browser: \(displayName)"
        destinationBrowserLabel.setAccessibilityLabel(destinationBrowserLabel.stringValue)
    }

    // Set only display state. Callers own the scan lifecycle and Cancel action.
    func show(documentDescription: String, stage: ScanProgressStage = .queued,
              activeScans: Int = 0) {
        filenameLabel.stringValue = documentDescription
        stageLabel.stringValue = stage.label
        // Count only processes confirmed launched by the native owner, never
        // queued documents, scheduled workers, or duplicate open events.
        let count = max(0, activeScans)
        activeScansLabel.stringValue = "Active scans: \(count)"
        activeScansLabel.setAccessibilityLabel(activeScansLabel.stringValue)
        orderFrontRegardless()
    }
}
