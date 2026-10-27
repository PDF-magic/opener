import AppKit

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

final class PDFOpener: NSObject, NSApplicationDelegate {
    private var pending = Set<String>()
    // Retain completed requests until exit, including events queued during a scan.
    private var received = Set<String>()
    // Retain the path supplied by Finder separately from the resolved scan target.
    private var requestedPaths = [String: String]()
    private var panel: NSPanel?
    private var filename: NSTextField?

    func applicationDidFinishLaunching(_ notification: Notification) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            if self.received.isEmpty { NSApp.terminate(nil) }
        }
    }

    private func showProgress() {
        if panel == nil {
            let window = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 360, height: 300),
                                 styleMask: [.titled], backing: .buffered, defer: false)
            window.title = "PDF Magic Opener — Scanning"
            window.level = .floating
            // Finder or Brave stays active while this accessory app scans.
            window.hidesOnDeactivate = false
            window.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
            window.isReleasedWhenClosed = false
            let reading = TwilightReadingView(frame: NSRect(x: 30, y: 82, width: 300, height: 205))
            window.contentView?.addSubview(reading)
            let title = NSTextField(labelWithString: "Checking for malware…")
            title.font = .systemFont(ofSize: 15, weight: .semibold)
            title.alignment = .center
            title.frame = NSRect(x: 20, y: 57, width: 320, height: 22)
            window.contentView?.addSubview(title)
            let label = NSTextField(labelWithString: "")
            label.alignment = .center
            label.lineBreakMode = .byTruncatingMiddle
            label.textColor = .secondaryLabelColor
            label.frame = NSRect(x: 20, y: 31, width: 320, height: 20)
            window.contentView?.addSubview(label)
            filename = label
            let progress = NSProgressIndicator(frame: NSRect(x: 30, y: 15, width: 300, height: 5))
            progress.style = .bar
            progress.isIndeterminate = true
            progress.startAnimation(nil)
            window.contentView?.addSubview(progress)
            panel = window
            window.center()
        }
        if pending.count == 1, let path = pending.first {
            filename?.stringValue = URL(fileURLWithPath: requestedPaths[path] ?? path).lastPathComponent
        } else {
            filename?.stringValue = "\(pending.count) documents"
        }
        panel?.orderFrontRegardless()
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        let script = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")
        for url in urls {
            let requestedPath = url.path
            let path = url.standardizedFileURL.resolvingSymlinksInPath().path
            guard received.insert(path).inserted else { continue }
            requestedPaths[path] = requestedPath
            pending.insert(path)
            showProgress()
            DispatchQueue.global(qos: .userInitiated).async {
                let process = Process()
                let errors = Pipe()
                process.executableURL = URL(fileURLWithPath: "/bin/bash")
                process.arguments = [script.path, path]
                process.standardError = errors
                process.standardOutput = FileHandle.nullDevice
                var message: String?
                do {
                    try process.run()
                    let output = errors.fileHandleForReading.readDataToEndOfFile()
                    process.waitUntilExit()
                    if process.terminationStatus != 0 {
                        message = String(data: output, encoding: .utf8) ?? "The malware scan could not finish."
                    }
                } catch {
                    message = error.localizedDescription
                }
                let failure = message
                DispatchQueue.main.async {
                    self.pending.remove(path)
                    if self.pending.isEmpty { self.panel?.orderOut(nil) }
                    else { self.showProgress() }
                    if let failure = failure {
                        NSApp.activate(ignoringOtherApps: true)
                        let alert = NSAlert()
                        alert.alertStyle = .warning
                        alert.messageText = "Opening stopped"
                        alert.informativeText = failure
                        alert.addButton(withTitle: "OK")
                        alert.runModal()
                    }
                    if self.pending.isEmpty { NSApp.terminate(nil) }
                }
            }
        }
    }
}

let app = NSApplication.shared
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
