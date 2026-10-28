import AppKit
import Carbon.HIToolbox
import UserNotifications

// The native PDF owner (not the standalone Settings app) requests macOS
// notification authorization on the first opted-in successful handoff.
// Notification delivery is best effort, never part of the scan verdict.
// Never put document paths, names, or scan diagnostics in notifications.
func deliverSuccessfulScanNotification(completion: @escaping () -> Void) {
    let center = UNUserNotificationCenter.current()
    func enqueue() {
        let content = UNMutableNotificationContent()
        content.title = "PDF Magic Opener"
        content.body = "A PDF passed scanning and was handed off to your chosen application."
        let request = UNNotificationRequest(identifier: UUID().uuidString,
                                            content: content, trigger: nil)
        center.add(request) { _ in completion() }
    }
    center.getNotificationSettings { settings in
        switch settings.authorizationStatus {
        case .authorized, .provisional:
            enqueue()
        case .notDetermined:
            center.requestAuthorization(options: [.alert]) { allowed, _ in
                if allowed { enqueue() } else { completion() }
            }
        default:
            // Denied or restricted by macOS: never bypass system permissions.
            completion()
        }
    }
}

// This notice is optional and deliberately contains no scan diagnostics or file names.
func deliverBlockedFileNotification(completion: @escaping () -> Void) {
    let center = UNUserNotificationCenter.current()
    func enqueue() {
        let content = UNMutableNotificationContent()
        content.title = "PDF Magic Opener"
        content.body = "A PDF could not be opened because its safety check failed."
        let request = UNNotificationRequest(identifier: UUID().uuidString,
                                            content: content, trigger: nil)
        center.add(request) { _ in completion() }
    }
    center.getNotificationSettings { settings in
        switch settings.authorizationStatus {
        case .authorized, .provisional: enqueue()
        case .notDetermined:
            center.requestAuthorization(options: [.alert]) { allowed, _ in
                if allowed { enqueue() } else { completion() }
            }
        default: completion()
        }
    }
}

// A request's arrival time is distinct from its eventual clean-scan cache time.
struct ScanRequest {
    let requestTimestamp: Date
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
    // Count finished scan-gate requests, not completed malware approvals.
    private var finishedRequests = 0
    private let maxConcurrentScans = 2
    private var queued = [String]()
    private var running = Set<String>()
    // Main-thread-only: requests whose native scan-gate child has actually launched.
    private var launchedScans = Set<String>()
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
    private var panel: ScanProgressPanel?
    // Hold the native scan-gate stdin writer open while its owner is alive.
    private var scanLifetimes = [String: Pipe]()
    private var terminating = false
    private var pendingSuccessNotifications = 0

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
        launchedScans.removeAll()
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
        // Presentation only: hidden progress must not skip or cancel scans.
        // Each request still enters the unchanged queue and scanner gate.
        guard ScanProgressPreference.isEnabled() else {
            panel?.orderOut(nil)
            return
        }
        if panel == nil {
            panel = ScanProgressPanel(
                cancelTarget: self, cancelAction: #selector(cancelScans(_:)))
        }
        // Prefer a currently scanning file; use a queued request before launch.
        // Sorting makes the displayed filename stable when two scans run together.
        guard let path = running.sorted().first ?? queued.first ?? pending.sorted().first else {
            panel?.orderOut(nil)
            return
        }
        let filename = URL(fileURLWithPath: requestedPaths[path] ?? path).lastPathComponent
        let description = pending.count == 1
            ? filename
            : "\(filename) (\(pending.count) documents)"
        // A queued request is not a running scan; a scheduled worker is not
        // a launched scanner. Never infer an internal ClamAV substage.
        let stage: ScanProgressStage
        if !launchedScans.isEmpty {
            stage = .scanning
        } else if !running.isEmpty {
            stage = .starting
        } else {
            stage = .queued
        }
        panel?.show(documentDescription: description, stage: stage,
                    queuedDocumentCount: queued.count,
                    activeScans: launchedScans.count)
        // Per-document scanning percentages are unknown; batch completion is
        // measured using the actual finished and still-pending requests.
        let totalRequests = finishedRequests + pending.count
        let batchProgress: (completed: Int, total: Int)? = totalRequests > 1
            ? (completed: finishedRequests, total: totalRequests) : nil
        panel?.updateBatchProgress(batchProgress)
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
                    DispatchQueue.main.async {
                        // Cancel or completion may have already hidden the panel.
                        self.processLock.lock()
                        let cancelled = self.cancelledRequests.contains(path)
                        self.processLock.unlock()
                        guard !cancelled, !self.terminating, self.pending.contains(path) else {
                            return
                        }
                        self.launchedScans.insert(path)
                        self.showProgress()
                    }
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
                self.launchedScans.remove(path)
                self.processLock.lock()
                let wasCancelled = self.cancelledRequests.contains(path)
                self.processLock.unlock()
                if !wasCancelled { self.finishedRequests += 1 }
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
                // A nil error may also indicate cancellation. Only a zero
                // status scan-and-open completion with no cancellation can
                // publish an opt-in success notification.
                self.processLock.lock()
                let cancelled = self.cancelledRequests.contains(path)
                self.processLock.unlock()
                if BlockedFileNotificationPreference.shouldNotify(
                    failure: failure, cancelled: cancelled
                ) {
                    self.pendingSuccessNotifications += 1
                    deliverBlockedFileNotification { [weak self] in
                        DispatchQueue.main.async {
                            guard let self else { return }
                            self.pendingSuccessNotifications -= 1
                            if self.pending.isEmpty && self.pendingSuccessNotifications == 0 {
                                NSApp.terminate(nil)
                            }
                        }
                    }
                }
                if SuccessfulScanNotificationPreference.shouldNotify(
                    failure: failure, cancelled: cancelled
                ) {
                    self.pendingSuccessNotifications += 1
                    deliverSuccessfulScanNotification { [weak self] in
                        DispatchQueue.main.async {
                            guard let self else { return }
                            self.pendingSuccessNotifications -= 1
                            if self.pending.isEmpty && self.pendingSuccessNotifications == 0 {
                                NSApp.terminate(nil)
                            }
                        }
                    }
                }
                if self.pending.isEmpty && self.pendingSuccessNotifications == 0 {
                    NSApp.terminate(nil)
                }
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
        // Update the initial "queued" stage after dispatching scheduled work.
        if !pending.isEmpty { showProgress() }
    }
}

@main
struct PDFMagicOpenerEntry {
    static func main() {
        let app = NSApplication.shared
        let delegate = PDFOpener()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }
}
