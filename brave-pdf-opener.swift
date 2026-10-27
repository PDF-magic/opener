import AppKit
import Carbon.HIToolbox

// A request's arrival time is distinct from its eventual clean-scan cache time.
struct ScanRequest {
    let requestTimestamp: Date
}

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

// Clean up scan stderr pipes even if launching or reading from the scanner fails.
func withScanErrorPipe<Result>(_ operation: (Pipe) throws -> Result) rethrows -> Result {
    let errors = Pipe()
    defer {
        errors.fileHandleForReading.closeFile()
        errors.fileHandleForWriting.closeFile()
    }
    return try operation(errors)
}

// Preserve the sending application reported by macOS, never infer a source
// from the frontmost window or the file extension.
func requestSource(forBundleIdentifier identifier: String?) -> String {
    guard let identifier = identifier?.lowercased() else { return "unknown" }
    if identifier == "com.apple.finder" { return "finder" }
    let browsers: Set<String> = [
        "com.apple.safari", "com.apple.safarialternate", "com.brave.browser",
        "com.google.chrome", "com.google.chrome.canary",
        "org.mozilla.firefox", "org.mozilla.firefoxdeveloperedition",
        "com.microsoft.edgemac", "company.thebrowser.browser",
        "com.vivaldi.vivaldi", "com.operasoftware.opera"
    ]
    if browsers.contains(identifier) { return "browser" }
    if ["com.apple.dock", "com.apple.launchservicesd", "com.apple.loginwindow"].contains(identifier) {
        return "unknown"
    }
    return "desktop-application"
}

func currentRequestSource() -> String {
    guard let event = NSAppleEventManager.shared().currentAppleEvent else { return "unknown" }
    for keyword in [AEKeyword(keySenderPIDAttr), AEKeyword(keyAddressAttr)] {
        guard let bytes = event.attributeDescriptor(forKeyword: keyword)?
                .coerce(toDescriptorType: typeKernelProcessID)?.data,
              bytes.count == MemoryLayout<pid_t>.size else { continue }
        let pid = bytes.withUnsafeBytes { $0.loadUnaligned(as: pid_t.self) }
        if pid > 0 {
            return requestSource(forBundleIdentifier:
                NSRunningApplication(processIdentifier: pid)?.bundleIdentifier)
        }
    }
    return "unknown"
}

final class PDFOpener: NSObject, NSApplicationDelegate {
    private var pending = Set<String>()
    // Retain completed requests until exit, including events queued during a scan.
    private var received = Set<String>()
    private let maxConcurrentScans = 2
    private var queued = [String]()
    private var running = Set<String>()
    private let processLock = NSLock()
    private var activeProcesses = [String: Process]()
    private var cancelledRequests = Set<String>()
    // Retain the path supplied by Finder separately from the resolved scan target.
    private var requestedPaths = [String: String]()
    // Keep macOS-granted access alive while an external-volume PDF is queued or scanned.
    // Ordinary unscoped file URLs require no explicit release.
    private var securityScopedDocuments = [String: URL]()
    // Keep the macOS open-event sender for each queued request.
    private var requestOrigins = [String: String]()
    // Session-only metadata keyed by canonical path; duplicate events keep the first time.
    private(set) var scanRequests = [String: ScanRequest]()
    private var panel: NSPanel?
    private var filename: NSTextField?
    // Hold the native scan-gate stdin writer open while its owner is alive.
    private var scanLifetimes = [String: Pipe]()
    private var terminating = false

    func applicationWillTerminate(_ notification: Notification) {
        terminating = true
        for lifetime in scanLifetimes.values {
            try? lifetime.fileHandleForWriting.close()
        }
        scanLifetimes.removeAll()
        for url in securityScopedDocuments.values {
            url.stopAccessingSecurityScopedResource()
        }
        securityScopedDocuments.removeAll()
    }


    func applicationDidFinishLaunching(_ notification: Notification) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
            if self.received.isEmpty { NSApp.terminate(nil) }
        }
    }

    @objc private func cancelScans(_ sender: NSButton) {
        // Never start queued documents after cancellation, even when an
        // already-running scan releases capacity.
        for path in queued {
            pending.remove(path)
            requestedPaths.removeValue(forKey: path)
            requestOrigins.removeValue(forKey: path)
            scanRequests.removeValue(forKey: path)
            if let url = securityScopedDocuments.removeValue(forKey: path) {
                url.stopAccessingSecurityScopedResource()
            }
        }
        queued.removeAll()
        processLock.lock()
        for path in running {
            cancelledRequests.insert(path)
            if let process = activeProcesses[path], process.isRunning {
                process.terminate()
            }
        }
        processLock.unlock()
        panel?.orderOut(nil)
        if pending.isEmpty { NSApp.terminate(nil) }
    }

    private func showProgress() {
        if panel == nil {
            let window = NSPanel(contentRect: NSRect(x: 0, y: 0, width: 360, height: 338),
                                 styleMask: [.titled], backing: .buffered, defer: false)
            window.title = "PDF Magic Opener — Scanning"
            window.level = .floating
            // Finder or Brave stays active while this accessory app scans.
            window.hidesOnDeactivate = false
            window.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
            window.isReleasedWhenClosed = false
            let reading = TwilightReadingView(frame: NSRect(x: 30, y: 118, width: 300, height: 205))
            window.contentView?.addSubview(reading)
            let title = NSTextField(labelWithString: "Checking for malware…")
            title.font = .systemFont(ofSize: 15, weight: .semibold)
            title.alignment = .center
            title.frame = NSRect(x: 20, y: 93, width: 320, height: 22)
            window.contentView?.addSubview(title)
            let label = NSTextField(labelWithString: "")
            label.alignment = .center
            label.lineBreakMode = .byTruncatingMiddle
            label.textColor = .secondaryLabelColor
            label.frame = NSRect(x: 20, y: 67, width: 320, height: 20)
            window.contentView?.addSubview(label)
            filename = label
            let progress = NSProgressIndicator(frame: NSRect(x: 30, y: 51, width: 300, height: 5))
            progress.style = .bar
            progress.isIndeterminate = true
            progress.startAnimation(nil)
            window.contentView?.addSubview(progress)
            let cancel = NSButton(title: "Cancel", target: self, action: #selector(cancelScans(_:)))
            cancel.bezelStyle = .rounded
            cancel.frame = NSRect(x: 136, y: 8, width: 88, height: 28)
            window.contentView?.addSubview(cancel)
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

    private func startQueuedScans() {
        guard !terminating else { return }
        // All queue mutations happen on the application's main thread.
        while running.count < maxConcurrentScans && !queued.isEmpty {
            let path = queued.removeFirst()
            running.insert(path)
            startScan(path)
        }
    }

    private func startScan(_ path: String) {
        let origin = requestOrigins[path] ?? "unknown"
        let script = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")
        let lifetime = Pipe()
        scanLifetimes[path] = lifetime
        DispatchQueue.global(qos: .userInitiated).async {
            let failure = withScanErrorPipe { errors -> String? in
                let process = Process()
                process.standardInput = lifetime
                process.executableURL = URL(fileURLWithPath: "/bin/bash")
                process.arguments = [script.path, path]
                process.standardError = errors
                process.standardOutput = FileHandle.nullDevice
                var environment = ProcessInfo.processInfo.environment
                environment["PDF_MAGIC_NATIVE_CANCEL"] = "1"
                environment["PDF_MAGIC_PARENT_LIFETIME"] = "1"
                environment["PDF_MAGIC_REQUESTING_APPLICATION"] = "PDF Magic Opener"
                environment["PDF_MAGIC_REQUEST_ORIGIN"] = origin
                process.environment = environment

                // Synchronize launching with Cancel. Workers already dispatched
                // to the background cannot launch after a cancelled request.
                self.processLock.lock()
                if self.cancelledRequests.contains(path) {
                    self.processLock.unlock()
                    return nil
                }
                do {
                    try process.run()
                    self.activeProcesses[path] = process
                    self.processLock.unlock()
                } catch {
                    self.processLock.unlock()
                    return error.localizedDescription
                }
                errors.fileHandleForWriting.closeFile()
                let output = errors.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                self.processLock.lock()
                let cancelled = self.cancelledRequests.contains(path)
                self.activeProcesses.removeValue(forKey: path)
                self.processLock.unlock()
                if cancelled { return nil }
                if process.terminationStatus != 0 {
                    return String(data: output, encoding: .utf8) ?? "The malware scan could not finish."
                }
                return nil
            }
DispatchQueue.main.async {
                if let pipe = self.scanLifetimes.removeValue(forKey: path) {
                    try? pipe.fileHandleForWriting.close()
                }
                self.running.remove(path)
                self.pending.remove(path)
                self.requestedPaths.removeValue(forKey: path)
                self.requestOrigins.removeValue(forKey: path)
                if let url = self.securityScopedDocuments.removeValue(forKey: path) {
                    url.stopAccessingSecurityScopedResource()
                }
                // Release capacity and start the next queued document even after a failure.
                self.startQueuedScans()
                self.processLock.lock()
                let hasUncancelled = self.pending.contains { !self.cancelledRequests.contains($0) }
                self.processLock.unlock()
                if hasUncancelled { self.showProgress() }
                else { self.panel?.orderOut(nil) }
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

    func application(_ application: NSApplication, open urls: [URL]) {
        let origin = currentRequestSource()
        for url in urls {
            guard !terminating else { break }
            guard url.isFileURL else { continue }
            // Retain the original URL's security scope, if provided by macOS.
            // Resolving symlinks produces a separate URL without that grant.
            let hasSecurityScope = url.startAccessingSecurityScopedResource()
            let requestedPath = url.path
            let path = url.standardizedFileURL.resolvingSymlinksInPath().path
            guard received.insert(path).inserted else {
                if hasSecurityScope { url.stopAccessingSecurityScopedResource() }
                continue
            }
            if hasSecurityScope { securityScopedDocuments[path] = url }
            requestedPaths[path] = requestedPath
            requestOrigins[path] = origin
            scanRequests[path] = ScanRequest(requestTimestamp: Date())
            pending.insert(path)
            queued.append(path)
            showProgress()
        }
        startQueuedScans()
    }
}

let app = NSApplication.shared
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
