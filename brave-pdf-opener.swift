import AppKit

// Draw the reading loop locally so the scan indicator needs no network or image files.
final class TwilightReadingView: NSView {
    private var timer: Timer?
    private let started = Date()

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
        let purple = NSColor(calibratedRed: 0.65, green: 0.43, blue: 0.84, alpha: 1)
        let mane = NSColor(calibratedRed: 0.17, green: 0.15, blue: 0.38, alpha: 1)
        let pink = NSColor(calibratedRed: 0.94, green: 0.25, blue: 0.64, alpha: 1)
        func ellipse(_ rect: NSRect, _ color: NSColor) {
            color.setFill(); NSBezierPath(ovalIn: rect).fill()
        }
        func polygon(_ points: [NSPoint], _ color: NSColor) {
            let path = NSBezierPath()
            path.move(to: points[0])
            for point in points.dropFirst() { path.line(to: point) }
            path.close(); color.setFill(); path.fill()
        }
        func line(_ points: [NSPoint], _ color: NSColor, _ width: CGFloat = 2) {
            let path = NSBezierPath()
            path.move(to: points[0])
            for point in points.dropFirst() { path.line(to: point) }
            color.setStroke(); path.lineWidth = width; path.lineCapStyle = .round; path.stroke()
        }
        ellipse(NSRect(x: 61, y: 12, width: 178, height: 14), purple.withAlphaComponent(0.12))
        ellipse(NSRect(x: 104, y: 36, width: 88, height: 73), purple)
        ellipse(NSRect(x: 86, y: 67 + bob, width: 119, height: 101), mane)
        // Ears, unicorn horn, face and Twilight's signature mane stripes.
        polygon([NSPoint(x: 101, y: 135 + bob), NSPoint(x: 100, y: 177 + bob), NSPoint(x: 130, y: 149 + bob)], purple)
        polygon([NSPoint(x: 173, y: 148 + bob), NSPoint(x: 197, y: 176 + bob), NSPoint(x: 195, y: 127 + bob)], purple)
        ellipse(NSRect(x: 108, y: 73 + bob, width: 88, height: 78), purple)
        polygon([NSPoint(x: 142, y: 145 + bob), NSPoint(x: 151, y: 190 + bob), NSPoint(x: 162, y: 145 + bob)], purple)
        line([NSPoint(x: 146, y: 159 + bob), NSPoint(x: 157, y: 163 + bob)], mane.withAlphaComponent(0.4), 1)
        line([NSPoint(x: 148, y: 171 + bob), NSPoint(x: 154, y: 174 + bob)], mane.withAlphaComponent(0.4), 1)
        polygon([NSPoint(x: 108, y: 148 + bob), NSPoint(x: 180, y: 151 + bob), NSPoint(x: 190, y: 124 + bob), NSPoint(x: 114, y: 125 + bob)], mane)
        polygon([NSPoint(x: 136, y: 149 + bob), NSPoint(x: 147, y: 149 + bob), NSPoint(x: 156, y: 126 + bob), NSPoint(x: 145, y: 126 + bob)], pink)
        polygon([NSPoint(x: 148, y: 149 + bob), NSPoint(x: 154, y: 149 + bob), NSPoint(x: 164, y: 126 + bob), NSPoint(x: 158, y: 126 + bob)], purple)
        let blink = phase.truncatingRemainder(dividingBy: 4) > 3.8
        for x: CGFloat in [129, 169] {
            if blink {
                line([NSPoint(x: x - 9, y: 111 + bob), NSPoint(x: x + 9, y: 111 + bob)], mane)
            } else {
                ellipse(NSRect(x: x - 9, y: 102 + bob, width: 18, height: 18), .white)
                ellipse(NSRect(x: x - 4 + sin(phase) * 2, y: 102 + bob, width: 9, height: 12), mane)
            }
            let glasses = NSBezierPath(ovalIn: NSRect(x: x - 15, y: 97 + bob, width: 30, height: 27))
            mane.setStroke(); glasses.lineWidth = 2; glasses.stroke()
        }
        line([NSPoint(x: 144, y: 112 + bob), NSPoint(x: 154, y: 112 + bob)], mane)
        line([NSPoint(x: 145, y: 87 + bob), NSPoint(x: 151, y: 84 + bob), NSPoint(x: 157, y: 87 + bob)], mane, 1.5)
        // Floating open magic book, with a page turning continuously.
        let bookY = 34 + sin(phase * 2) * 3
        polygon([NSPoint(x: 75, y: bookY + 39), NSPoint(x: 147, y: bookY + 27), NSPoint(x: 223, y: bookY + 39), NSPoint(x: 221, y: bookY - 2), NSPoint(x: 147, y: bookY - 14), NSPoint(x: 77, y: bookY - 2)], mane)
        polygon([NSPoint(x: 80, y: bookY + 41), NSPoint(x: 147, y: bookY + 30), NSPoint(x: 216, y: bookY + 41), NSPoint(x: 215, y: bookY + 3), NSPoint(x: 147, y: bookY - 8), NSPoint(x: 82, y: bookY + 3)], NSColor(calibratedRed: 1, green: 0.95, blue: 0.81, alpha: 1))
        line([NSPoint(x: 147, y: bookY + 30), NSPoint(x: 147, y: bookY - 8)], purple, 1)
        for offset: CGFloat in [10, 19, 28] {
            line([NSPoint(x: 91, y: bookY + offset), NSPoint(x: 135, y: bookY + offset - 7)], purple.withAlphaComponent(0.5), 1)
            line([NSPoint(x: 159, y: bookY + offset - 7), NSPoint(x: 206, y: bookY + offset)], purple.withAlphaComponent(0.5), 1)
        }
        let turn = sin(phase * 2.5)
        polygon([NSPoint(x: 147, y: bookY - 7), NSPoint(x: 147, y: bookY + 30), NSPoint(x: 147 + turn * 63, y: bookY + 44), NSPoint(x: 147 + turn * 63, y: bookY + 7)], NSColor(calibratedWhite: 1, alpha: 0.8))
        ellipse(NSRect(x: 91, y: bookY + 22, width: 24, height: 13), purple)
        ellipse(NSRect(x: 190, y: bookY + 22, width: 24, height: 13), purple)
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
            window.title = "Twilight is checking your document"
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
        filename?.stringValue = pending.count == 1 ? URL(fileURLWithPath: pending.first!).lastPathComponent : "\(pending.count) documents"
        panel?.orderFrontRegardless()
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        let script = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")
        for url in urls {
            let path = url.standardizedFileURL.resolvingSymlinksInPath().path
            guard received.insert(path).inserted else { continue }
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
