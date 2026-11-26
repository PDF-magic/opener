import AppKit
import Foundation

// This app is the scan gate, never an approved destination for its own PDFs.
private let openerBundleIdentifier = "local.studio.brave-pdf-opener"

// This helper launches only paths supplied after scanner approval.
final class LaunchCompletion: @unchecked Sendable {
    private let lock = NSLock()
    private var value: Bool?

    func finish(_ app: NSRunningApplication?, error: Error?) {
        lock.lock()
        value = app != nil && error == nil
        lock.unlock()
    }

    var result: Bool? {
        lock.lock()
        defer { lock.unlock() }
        return value
    }

    func waitForCompletion() -> Bool {
        // NSWorkspace completions may be dispatched on the main thread.
        let deadline = Date().addingTimeInterval(30)
        while Date() < deadline {
            if let value = result { return value }
            _ = RunLoop.current.run(mode: .default, before: min(deadline, Date().addingTimeInterval(0.05)))
        }
        return result ?? false
    }
}


 // Resolve only registered and executable .app bundles. Finder registration
 // alone is not proof that the app remains installed at its recorded URL.
func resolveTargetApplication(
    bundleIdentifier: String,
    lookup: ((String) -> URL?)? = nil,
    lookupAll: ((String) -> [URL])? = nil
) -> URL? {
    guard !bundleIdentifier.isEmpty, bundleIdentifier != openerBundleIdentifier else {
        return nil
    }

    let candidates: [URL]
    if let lookupAll = lookupAll {
        candidates = lookupAll(bundleIdentifier)
    } else if let lookup = lookup {
        // Preserve the single-location test hook for existing callers.
        candidates = lookup(bundleIdentifier).map { [$0] } ?? []
    } else {
        candidates = NSWorkspace.shared.urlsForApplications(withBundleIdentifier: bundleIdentifier)
    }
    // Launch Services ranks all registered copies by suitability. Skip stale
    // registrations, mismatched IDs, and nonexecutable bundles while retaining
    // that order; never substitute another browser or the PDF scan gate.
    for candidate in candidates {
        guard candidate.isFileURL else { continue }
        let target = candidate.standardizedFileURL.resolvingSymlinksInPath()
        var isDirectory: ObjCBool = false
        guard target.pathExtension.lowercased() == "app",
              FileManager.default.fileExists(atPath: target.path, isDirectory: &isDirectory),
              isDirectory.boolValue,
              let bundle = Bundle(url: target),
              bundle.bundleIdentifier == bundleIdentifier,
              let executable = bundle.executableURL,
              FileManager.default.isExecutableFile(atPath: executable.path) else { continue }
        return target
    }
    return nil
}

// Inspect metadata only. Reading an iCloud placeholder can itself start a
// download, so this check must precede any content fingerprinting or scanning.
func downloadStatusAllowsOpen(
    isUbiquitous: Bool?,
    downloadingStatus: URLUbiquitousItemDownloadingStatus?,
    isDownloading: Bool?
) -> Bool {
    guard isUbiquitous == true else { return true }
    guard let status = downloadingStatus,
          status == .current || status == .downloaded else { return false }
    // A stale copy may exist, but must not be scanned during an update.
    return isDownloading != true
}

func isLocallyAvailablePDF(_ url: URL) -> Bool {
    guard url.isFileURL, url.pathExtension.lowercased() == "pdf" else { return false }
    do {
        let values = try url.resourceValues(forKeys: [
            .isRegularFileKey,
            .isUbiquitousItemKey,
            .ubiquitousItemDownloadingStatusKey,
            .ubiquitousItemIsDownloadingKey,
        ])
        return values.isRegularFile == true && downloadStatusAllowsOpen(
            isUbiquitous: values.isUbiquitousItem,
            downloadingStatus: values.ubiquitousItemDownloadingStatus,
            isDownloading: values.ubiquitousItemIsDownloading
        )
    } catch {
        // Files whose availability cannot be checked must not be launched.
        return false
    }
}

// Compare the pre-scan identity to the filesystem object at native handoff.
// The scanner separately verified complete bytes and every app-bundle member.
func identityMatches(_ path: String, expected: String?) -> Bool {
    guard let expected = expected else { return true }
    guard !expected.isEmpty && expected.utf8.count <= 256 else { return false }
    var info = stat()
    guard lstat(path, &info) == 0 else { return false }
    let actual = [
        String(info.st_dev),
        String(info.st_ino),
        String(info.st_mode & 0o170000),
        String(info.st_size),
        String(Int64(info.st_mtimespec.tv_sec) * 1_000_000_000 +
               Int64(info.st_mtimespec.tv_nsec)),
        String(Int64(info.st_ctimespec.tv_sec) * 1_000_000_000 +
               Int64(info.st_ctimespec.tv_nsec)),
    ]
    return expected == actual.joined(separator: ":")
}

func launch(_ arguments: [String], workspace: NSWorkspace = .shared,
            applicationLookup: ((String) -> URL?)? = nil) -> Bool {
    var options = arguments
    var expectedIdentity: String?
    if options.count >= 2 && options[0] == "--expected-identity" {
        expectedIdentity = options[1]
        options.removeFirst(2)
    }
    if options.count == 2 && options[0] == "--check-local" {
        let path = options[1]
        return path.hasPrefix("/") && identityMatches(path, expected: expectedIdentity)
            && isLocallyAvailablePDF(URL(fileURLWithPath: path))
    }
    let path: String
    let bundleIdentifier: String?
    if options.count == 1 {
        path = options[0]
        bundleIdentifier = nil
    } else if options.count == 3 && options[0] == "--bundle-id" && !options[1].isEmpty {
        bundleIdentifier = options[1]
        path = options[2]
    } else {
        return false
    }

    guard path.hasPrefix("/") && identityMatches(path, expected: expectedIdentity) else {
        return false
    }
    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory) else { return false }
    let target = URL(fileURLWithPath: path)
    let isApplication = isDirectory.boolValue && target.pathExtension.lowercased() == "app"
    guard !isDirectory.boolValue || isApplication else { return false }
    // Recheck immediately before NSWorkspace gets a chance to launch a browser.
    if target.pathExtension.lowercased() == "pdf" && !isLocallyAvailablePDF(target) {
        return false
    }
    let config = NSWorkspace.OpenConfiguration()
    let completed = LaunchCompletion()

    if let bundleIdentifier = bundleIdentifier {
        // Use the same explicit app-specific NSWorkspace handoff regardless
        // of whether that browser already has a running process.
        // A test-only lookup can supply an isolated .app without changing
        // the installed application's Launch Services registration.
        let lookup = applicationLookup ?? { (identifier: String) in
            workspace.urlForApplication(withBundleIdentifier: identifier)
        }
        guard !isApplication,
              let appURL = resolveTargetApplication(bundleIdentifier: bundleIdentifier,
                                                    lookup: lookup) else {
            return false
        }
        guard identityMatches(path, expected: expectedIdentity) else { return false }
        workspace.open([target], withApplicationAt: appURL, configuration: config) {
            application, error in
            completed.finish(application, error: error)
        }
        return completed.waitForCompletion()
    }
    // PDFs must have an explicit, non-opener destination. Default PDF
    // handlers may point back to this scan gate and recursively rescan.
    if target.pathExtension.lowercased() == "pdf" { return false }
    if isApplication {
        // A direct .app launch must not restart the scan gate itself.
        guard Bundle(url: target)?.bundleIdentifier != openerBundleIdentifier else { return false }
        guard identityMatches(path, expected: expectedIdentity) else { return false }
        workspace.openApplication(at: target, configuration: config) {
            application, error in
            completed.finish(application, error: error)
        }
        return completed.waitForCompletion()
    }
    // Protect default-handler launches too if a non-PDF type is associated
    // with the opener; leave other system-default associations unchanged.
    if let handler = workspace.urlForApplication(toOpen: target),
       Bundle(url: handler)?.bundleIdentifier == openerBundleIdentifier {
        return false
    }
    guard identityMatches(path, expected: expectedIdentity) else { return false }
    return workspace.open(target)
}

guard launch(Array(CommandLine.arguments.dropFirst())) else {
    fputs("macOS could not open the approved item.\n", stderr)
    exit(EXIT_FAILURE)
}
