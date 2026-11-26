import AppKit
import Carbon.HIToolbox
import UserNotifications
import CryptoKit
import Darwin

// BEGIN NATIVE DIRECT PROCESS GATE
// A PDF scan may use the full 30-minute ClamAV policy deadline. Keep the
// native process ceiling above that budget to allow admission and handoff.
let nativeScanProcessTimeout: TimeInterval = 35 * 60
let nativeOriginProcessTimeout: TimeInterval = 2

// Foundation Process has no built-in execution timeout. A bounded wait first
// requests ordinary termination, then uses SIGKILL if the child ignores it.
// The semaphore is installed as the termination handler *before* process.run().
func waitForNativeProcess(_ process: Process, completion: DispatchSemaphore,
                          timeout: TimeInterval) -> Bool {
    if completion.wait(timeout: .now() + timeout) == .success {
        process.waitUntilExit()
        return true
    }
    if process.isRunning { process.terminate() }
    if completion.wait(timeout: .now() + 1) == .timedOut {
        if process.isRunning { _ = Darwin.kill(process.processIdentifier, SIGKILL) }
        _ = completion.wait(timeout: .now() + 2)
    }
    return false
}

// Drain scanner diagnostics while the bounded wait is active. A child that
// writes to stderr cannot deadlock the parent before its execution deadline.
// If a descendant retains the pipe, return after a bounded EOF grace period.
final class NativeScanDiagnostics {
    private let lock = NSLock()
    private var collected = Data()
    private let reachedEOF = DispatchSemaphore(value: 0)

    func begin(_ pipe: Pipe) {
        pipe.fileHandleForReading.readabilityHandler = { [self] reader in
            let chunk = reader.availableData
            lock.lock()
            collected.append(chunk)
            lock.unlock()
            if chunk.isEmpty {
                reader.readabilityHandler = nil
                reachedEOF.signal()
            }
        }
    }

    func finish(_ pipe: Pipe) -> Data {
        _ = reachedEOF.wait(timeout: .now() + 1)
        pipe.fileHandleForReading.readabilityHandler = nil
        lock.lock()
        defer { lock.unlock() }
        return collected
    }
}

// The native app uses Foundation's Process directly, not a shell script.
// Finder's Run Shell Script action remains a separate macOS integration.
func makeNativeScanProcess(script: URL, path: String, lifetime: Pipe,
                           errors: Pipe, environment: [String: String]) -> Process {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    process.arguments = [script.path, path]
    process.standardInput = lifetime
    process.standardError = errors
    process.standardOutput = FileHandle.nullDevice
    process.environment = environment
    return process
}

// Preserve the existing best-effort anonymous origin record without routing
// the actual scanner through Bash. Metadata failure must not block scanning.
func recordNativeScanOrigin(script: URL, path: String, environment: [String: String]) {
    guard FileManager.default.fileExists(atPath: script.path) else { return }
    let recorder = Process()
    recorder.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    recorder.arguments = [script.path, path]
    recorder.standardInput = FileHandle.nullDevice
    recorder.standardOutput = FileHandle.nullDevice
    recorder.standardError = FileHandle.nullDevice
    recorder.environment = environment
    let finished = DispatchSemaphore(value: 0)
    recorder.terminationHandler = { _ in finished.signal() }
    do {
        try recorder.run()
        _ = waitForNativeProcess(recorder, completion: finished,
                                 timeout: nativeOriginProcessTimeout)
    } catch {
        // Origin recording is advisory, never a second scanner policy.
    }
}
// END NATIVE DIRECT PROCESS GATE

// The native PDF owner (not the standalone Settings app) requests macOS
// notification authorization on the first opted-in delivery. Injecting only
// the system-notification transport lets headless tests exercise the real
// permission and delivery paths after the independent Settings app has quit.
// Scanner verdicts and preferences are never read or changed by this transport.
// Opaque per-document and verified-outcome IDs keep system deduplication
// independent of sensitive paths, user preferences and scanner verdicts.
func scanNotificationIdentifier(path: String, kind: String) -> String {
    let digest = SHA256.hash(data: Data(path.utf8))
    let opaquePath = digest.map { String(format: "%02x", $0) }.joined()
    return "pdf-magic-opener.scan.\(kind).\(opaquePath)"
}

struct NativeScanNotificationTransport {
    let getAuthorizationStatus: (@escaping (UNAuthorizationStatus) -> Void) -> Void
    let requestAuthorization: (@escaping (Bool) -> Void) -> Void
    let add: (UNNotificationRequest, @escaping () -> Void) -> Void

    static func system() -> NativeScanNotificationTransport {
        let center = UNUserNotificationCenter.current()
        return NativeScanNotificationTransport(
            getAuthorizationStatus: { callback in
                center.getNotificationSettings { callback($0.authorizationStatus) }
            },
            requestAuthorization: { callback in
                center.requestAuthorization(options: [.alert]) { allowed, _ in
                    callback(allowed)
                }
            },
            add: { request, callback in
                // The real Notification Center can outlive this helper process.
                // Ignore recent or still-pending identical notices; never
                // change the scanner verdict or mandatory failure warning.
                center.getDeliveredNotifications { delivered in
                    center.getPendingNotificationRequests { pending in
                        let recent = delivered.map {
                            (identifier: $0.request.identifier, date: $0.date)
                        }
                        guard ScanNotificationDeduplication.shouldQueue(
                            identifier: request.identifier,
                            delivered: recent,
                            pendingIdentifiers: pending.map { $0.identifier },
                            now: Date()
                        ) else {
                            callback()
                            return
                        }
                        center.add(request) { _ in callback() }
                    }
                }
            }
        )
    }
}

// Best-effort macOS notice: no document names, paths or scan diagnostics.
// Notification permission is independent of the SwiftUI preferences process.
private func enqueueNativeScanNotification(
    body: String,
    identifier: String,
    transport: NativeScanNotificationTransport,
    completion: @escaping () -> Void
) {
    func enqueue() {
        let content = UNMutableNotificationContent()
        content.title = "PDF Magic Opener"
        content.body = body
        let request = UNNotificationRequest(identifier: identifier,
                                            content: content, trigger: nil)
        transport.add(request, completion)
    }
    transport.getAuthorizationStatus { status in
        switch status {
        case .authorized, .provisional:
            enqueue()
        case .notDetermined:
            transport.requestAuthorization { allowed in
                if allowed { enqueue() } else { completion() }
            }
        default:
            // Denied or restricted by macOS: never bypass system permissions.
            completion()
        }
    }
}

func deliverSuccessfulScanNotification(
    identifier: String = UUID().uuidString,
    transport: NativeScanNotificationTransport = .system(),
    completion: @escaping () -> Void
) {
    enqueueNativeScanNotification(
        body: "A PDF passed scanning and was handed off to your chosen application.",
        identifier: identifier, transport: transport, completion: completion
    )
}

// Optional blocked-file notice, separate from the mandatory failure alert.
func deliverBlockedFileNotification(malwareDetected: Bool, scanFailed: Bool,
    sanitizerFailed: Bool = false,
    identifier: String = UUID().uuidString,
    transport: NativeScanNotificationTransport = .system(),
    completion: @escaping () -> Void
) {
    enqueueNativeScanNotification(
        body: malwareDetected
            ? "Malware was detected. The PDF was blocked and was not opened."
            : (sanitizerFailed
                ? "PDF sanitization failed. No sanitized copy was produced. This is not a malware detection."
                : (scanFailed
                    ? "A PDF scan failed or could not finish. The file was not opened."
                    : "A PDF could not be opened because its safety check failed.")),
        identifier: identifier, transport: transport, completion: completion
    )
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

// Initialization diagnostics are selected from known, path-free scanner messages.
// Do not present arbitrary process errors as verified initialization diagnoses.
enum ScannerInitializationError {
    static let missingHelper = "The installed scan helper is missing. Reinstall PDF Magic Opener."
    static let launchFailed = "The scan helper could not start. Reinstall PDF Magic Opener."

    private static let knownScannerMessages: Set<String> = [
        "ClamAV is unavailable. Run the Allow and Open installer again.",
        "Malware signatures are unavailable. Run update-malware-signatures.sh.",
        "Malware signatures have not been checked in 48 hours. Run update-malware-signatures.sh.",
        "The malware signature database is incomplete. Run update-malware-signatures.sh.",
        "ClamAV scanner version could not be verified. Reinstall ClamAV before opening files.",
        "Unsupported ClamAV scanner version. Install ClamAV 1.4 or 1.5 before opening files."
    ]

    static func displayedMessage(for failure: String) -> String? {
        let message = failure.trimmingCharacters(in: .whitespacesAndNewlines)
        if message == missingHelper || message == launchFailed ||
            knownScannerMessages.contains(message) {
            return message
        }
        return nil
    }
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

// The installed Python scan gate emits fixed, path-free denials, sometimes
// prefixed with a trusted request index. Never render arbitrary stderr:
// Python tracebacks can contain private paths, source lines and PDF metadata.
// Unknown diagnostics remain failures but receive a fixed explanation.
private enum NativeScanFailureDetails {
    static let unexpected = "The scanner returned an unexpected error; opening was stopped."
    static let empty = "The scan or file handoff returned no additional error details."

    private static let approved: Set<String> = [
        "Malware was detected; opening was stopped.",
        "Malware or an unscannable item was detected; opening was stopped.",
        "The scanner flagged a suspicious or unscannable item; opening was stopped.",
        "The malware scan could not finish; opening was stopped.",
        "The malware scan did not confirm a complete scan; opening was stopped.",
        "The malware scan timed out; opening was stopped.",
        "The scan was cancelled; opening was stopped.",
        "The request could not be processed; opening was stopped.",
        "The requested PDF is not available locally; opening was stopped.",
        "The selected file is unreadable; opening was stopped.",
        "The selected file or application does not exist; opening was stopped.",
        "The selected filesystem volume is unavailable; opening was stopped.",
        "The selected file became unavailable during scanning; opening was stopped.",
        "The file changed while checking it; opening was stopped. Try again.",
        "The file exceeds the 512 MB scan limit; opening was stopped.",
        "A zero-length file cannot be scanned; opening was stopped.",
        "The clean scan cache could not be verified; opening was stopped.",
        "Unable to record the scan destination; opening was stopped.",
        "The scan queue is unavailable; opening was stopped.",
        "Application bundle contains a link outside the bundle; opening was stopped.",
        "Only regular files and application bundles can be scanned.",
        "Select a file or application, rather than a folder."
    ]

    static func display(_ details: String) -> String {
        let reason = details.trimmingCharacters(in: .whitespacesAndNewlines)
        if reason.isEmpty { return empty }
        if let known = ScannerInitializationError.displayedMessage(for: reason) {
            return known
        }
        var candidate = reason
        if candidate.hasPrefix("Scan request ") {
            let fields = candidate.dropFirst("Scan request ".count)
                .split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
            guard fields.count == 2,
                  let index = Int(fields[0]), index > 0,
                  String(index) == String(fields[0]),
                  fields[1].hasPrefix(" ") else { return unexpected }
            candidate = String(fields[1].dropFirst())
        }
        return approved.contains(candidate) ? candidate : unexpected
    }
}

// Present the requested filename, not the canonical scan target or a generic
// progress count. Failure alerts remain visible even if progress is disabled.
func makeScanFailureAlert(requestedPath: String, details: String) -> NSAlert {
    let filename = URL(fileURLWithPath: requestedPath).lastPathComponent
    let reason = details.trimmingCharacters(in: .whitespacesAndNewlines)
    let explanation = NativeScanFailureDetails.display(reason)
    let alert = NSAlert()
    alert.alertStyle = .critical
    alert.messageText = "PDF could not be opened"
    alert.informativeText = "File: \(filename)\n\nThe safety scan or destination handoff failed. "
        + "PDF Magic Opener did not open this file.\n\nDetails: \(explanation)"
    if let initialization = ScannerInitializationError.displayedMessage(for: reason) {
        alert.messageText = "Scanner initialization failed"
        alert.informativeText = "File: \(filename)\n\nThe scanner could not initialize. "
            + "PDF Magic Opener did not open this file.\n\nDetails: \(initialization)"
    }
    alert.addButton(withTitle: "OK")
    return alert
}

final class PDFOpener: NSObject, NSApplicationDelegate {
    private var pending = Set<String>()
    // Retain completed requests until exit, including events queued during a scan.
    private var received = Set<String>()
    // A finished request is not necessarily a safe or approved document.
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
    // UI-only acknowledgement; scanner and launch policy remain unchanged.
    private var attentionRequired = false
    private var attentionDocumentName = ""
    // Hold the native scan-gate stdin writer open while its owner is alive.
    private var scanLifetimes = [String: Pipe]()
    private var terminating = false
    private var pendingSuccessNotifications = 0
    // Transient synchronized reservation also closes local callback races.
    private let notificationReservations = ScanNotificationReservation()

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
        // Once scanning finishes, Close explicitly acknowledges a blocked file.
        if pending.isEmpty && attentionRequired {
            attentionRequired = false
            panel?.orderOut(nil)
            if pendingSuccessNotifications == 0 { NSApp.terminate(nil) }
            return
        }
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
            // Future trusted Maximum producers call the panel failure hook.
            // Do not confuse their failure with a ClamAV malware verdict or
            // send an optional notice unless the existing blocked-file setting
            // is explicitly enabled. Built-in scans never enter this path.
            panel?.onVerifiedMaximumSanitizationFailure = { [weak self] in
                guard let self, BlockedFileNotificationPreference.isEnabled() else { return }
                self.pendingSuccessNotifications += 1
                deliverBlockedFileNotification(malwareDetected: false, scanFailed: false,
                                               sanitizerFailed: true) { [weak self] in
                    DispatchQueue.main.async {
                        guard let self else { return }
                        self.pendingSuccessNotifications -= 1
                        if self.pending.isEmpty && self.pendingSuccessNotifications == 0 && !self.attentionRequired {
                            NSApp.terminate(nil)
                        }
                    }
                }
            }
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
        // Display the read-only selection, never substitute a launch destination.
        panel?.updateDestinationBrowser(SelectedDestinationBrowser.displayName())
        panel?.show(documentDescription: description, stage: stage,
                    queuedDocumentCount: queued.count,
                    activeScans: launchedScans.count)
        // The scan gate provides no per-file percentage; only requests
        // actually finished within a multi-document batch are measurable.
        let totalRequests = finishedRequests + pending.count
        let batchProgress: (completed: Int, total: Int)? = totalRequests > 1
            ? (completed: finishedRequests, total: totalRequests) : nil
        panel?.updateBatchProgress(batchProgress)
    }

    // Presentation-only. Never read UI preferences from the scan-gate path.
    private func noteAttentionRequired(for path: String) {
        guard panel != nil, ScanProgressPreference.isEnabled() else { return }
        attentionRequired = true
        attentionDocumentName = URL(
            fileURLWithPath: requestedPaths[path] ?? path
        ).lastPathComponent
    }

    private func updateProgressAfterCompletion(hasUncancelled: Bool) {
        if hasUncancelled {
            showProgress()
        } else if attentionRequired && ScanProgressPreference.isEnabled() {
            panel?.showAttentionRequired(documentDescription: attentionDocumentName)
        } else {
            attentionRequired = false
            panel?.orderOut(nil)
        }
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
            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/scan-and-open.py")
        let originScript = script.deletingLastPathComponent()
            .appendingPathComponent("record-scan-origin.py")
        let lifetime = Pipe()
        scanLifetimes[path] = lifetime
        DispatchQueue.global(qos: .userInitiated).async {
            let failure = withScanErrorPipe { errors -> String? in
                var environment = ProcessInfo.processInfo.environment
                environment["PDF_MAGIC_NATIVE_CANCEL"] = "1"
                environment["PDF_MAGIC_PARENT_LIFETIME"] = "1"
                environment["PDF_MAGIC_REQUESTING_APPLICATION"] = "PDF Magic Opener"
                environment["PDF_MAGIC_REQUEST_ORIGIN"] = origin
                let process = makeNativeScanProcess(
                    script: script, path: path, lifetime: lifetime,
                    errors: errors, environment: environment)
                let finished = DispatchSemaphore(value: 0)
                process.terminationHandler = { _ in finished.signal() }
                let diagnostic = NativeScanDiagnostics()
                diagnostic.begin(errors)

                // Synchronize launching with Cancel. Workers already dispatched
                // to the background cannot launch after a cancelled request.
                self.processLock.lock()
                if self.cancelledRequests.contains(path) {
                    self.processLock.unlock()
                    _ = diagnostic.finish(errors)
                    return nil
                }
                var isDirectory: ObjCBool = false
                guard FileManager.default.fileExists(atPath: script.path, isDirectory: &isDirectory),
                      !isDirectory.boolValue else {
                    self.processLock.unlock()
                    _ = diagnostic.finish(errors)
                    return ScannerInitializationError.missingHelper
                }
                do {
                    try process.run()
                    self.activeProcesses[path] = process
                    self.processLock.unlock()
                    // Retain the wrapper's best-effort origin audit, but use
                    // a direct Python process instead of an additional shell.
                    recordNativeScanOrigin(script: originScript, path: path,
                                           environment: environment)
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
                    _ = diagnostic.finish(errors)
                    return ScannerInitializationError.launchFailed
                }
                errors.fileHandleForWriting.closeFile()
                let finishedInTime = waitForNativeProcess(
                    process, completion: finished, timeout: nativeScanProcessTimeout)
                let output = diagnostic.finish(errors)
                self.processLock.lock()
                let cancelled = self.cancelledRequests.contains(path)
                self.activeProcesses.removeValue(forKey: path)
                self.processLock.unlock()
                if cancelled { return nil }
                if !finishedInTime {
                    return "The malware scan exceeded its execution timeout; opening was stopped."
                }
                if process.terminationStatus != 0 {
                    return String(data: output, encoding: .utf8) ?? "The malware scan could not finish."
                }
                return nil
            }
DispatchQueue.main.async {
                if let pipe = self.scanLifetimes.removeValue(forKey: path) {
                    try? pipe.fileHandleForWriting.close()
                }
                // Capture the user's original filename before per-request cleanup.
                let requestedPath = self.requestedPaths[path] ?? path
                if failure != nil { self.noteAttentionRequired(for: path) }
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
                self.updateProgressAfterCompletion(hasUncancelled: hasUncancelled)
                if let failure = failure {
                    NSApp.activate(ignoringOtherApps: true)
                    let alert = makeScanFailureAlert(
                        requestedPath: requestedPath, details: failure)
                    alert.runModal()
                }
                // A nil error may also indicate cancellation. Only a zero
                // status scan-and-open completion with no cancellation can
                // publish an opt-in success notification.
                self.processLock.lock()
                let cancelled = self.cancelledRequests.contains(path)
                self.processLock.unlock()
                let blockedNotificationKind = BlockedFileNotificationPreference.notificationKind(
                    failure: failure, cancelled: cancelled
                )
                if blockedNotificationKind != .none {
                    let scanFailed = FailedScanNotificationClassification.shouldShowFailedScanNotice(
                        failure: failure, cancelled: cancelled
                    )
                    let kind = blockedNotificationKind == .malwareDetected
                        ? "malware" : (scanFailed ? "failed" : "blocked")
                    let identifier = scanNotificationIdentifier(path: path, kind: kind)
                    if self.notificationReservations.reserve(identifier) {
                        self.pendingSuccessNotifications += 1
                        deliverBlockedFileNotification(
                            malwareDetected: blockedNotificationKind == .malwareDetected,
                            scanFailed: scanFailed,
                            identifier: identifier
                        ) { [weak self] in
                            DispatchQueue.main.async {
                                guard let self else { return }
                                self.pendingSuccessNotifications -= 1
                                if self.pending.isEmpty && self.pendingSuccessNotifications == 0 && !self.attentionRequired {
                                    NSApp.terminate(nil)
                                }
                            }
                        }
                    }
                }
                if SuccessfulScanNotificationPreference.shouldNotify(
                    failure: failure, cancelled: cancelled
                ) {
                    let identifier = scanNotificationIdentifier(path: path, kind: "success")
                    if self.notificationReservations.reserve(identifier) {
                        self.pendingSuccessNotifications += 1
                        deliverSuccessfulScanNotification(identifier: identifier) { [weak self] in
                            DispatchQueue.main.async {
                                guard let self else { return }
                                self.pendingSuccessNotifications -= 1
                                if self.pending.isEmpty && self.pendingSuccessNotifications == 0 && !self.attentionRequired {
                                    NSApp.terminate(nil)
                                }
                            }
                        }
                    }
                }
                if self.pending.isEmpty && self.pendingSuccessNotifications == 0 && !self.attentionRequired {
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
