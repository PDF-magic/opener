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

final class ScanProgressPanel: NSPanel {
    let filenameLabel = NSTextField(labelWithString: "")
    let progressIndicator = NSProgressIndicator(frame: NSRect(x: 30, y: 51, width: 300, height: 5))
    let cancelButton: NSButton

    init(cancelTarget: AnyObject, cancelAction: Selector) {
        cancelButton = NSButton(title: "Cancel", target: cancelTarget, action: cancelAction)
        super.init(contentRect: NSRect(x: 0, y: 0, width: 360, height: 338),
                   styleMask: [.titled], backing: .buffered, defer: false)
        title = "PDF Magic Opener — Scanning"
        level = .floating
        hidesOnDeactivate = false
        collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        isReleasedWhenClosed = false
        contentView?.addSubview(TwilightReadingView(
            frame: NSRect(x: 30, y: 118, width: 300, height: 205)))
        let status = NSTextField(labelWithString: "Checking for malware…")
        status.font = .systemFont(ofSize: 15, weight: .semibold)
        status.alignment = .center
        status.frame = NSRect(x: 20, y: 93, width: 320, height: 22)
        contentView?.addSubview(status)
        filenameLabel.alignment = .center
        filenameLabel.lineBreakMode = .byTruncatingMiddle
        filenameLabel.textColor = .secondaryLabelColor
        filenameLabel.frame = NSRect(x: 20, y: 67, width: 320, height: 20)
        contentView?.addSubview(filenameLabel)
        progressIndicator.style = .bar
        progressIndicator.isIndeterminate = true
        progressIndicator.startAnimation(nil)
        contentView?.addSubview(progressIndicator)
        cancelButton.bezelStyle = .rounded
        cancelButton.frame = NSRect(x: 136, y: 8, width: 88, height: 28)
        contentView?.addSubview(cancelButton)
        center()
    }

    // Set only display text. Callers own the document queue and Cancel action.
    func show(documentDescription: String) {
        filenameLabel.stringValue = documentDescription
        orderFrontRegardless()
    }
}
