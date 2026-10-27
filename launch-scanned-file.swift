import AppKit
import Foundation

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
    lookup: (String) -> URL? = { NSWorkspace.shared.urlForApplication(withBundleIdentifier: $0) }
) -> URL? {
    guard !bundleIdentifier.isEmpty,
          let target = lookup(bundleIdentifier)?.standardizedFileURL.resolvingSymlinksInPath(),
          target.pathExtension.lowercased() == "app" else { return nil }

    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: target.path, isDirectory: &isDirectory),
          isDirectory.boolValue,
          let bundle = Bundle(url: target),
          bundle.bundleIdentifier == bundleIdentifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return nil }
    return target
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

func launch(_ arguments: [String], workspace: NSWorkspace = .shared) -> Bool {
    if arguments.count == 2 && arguments[0] == "--check-local" {
        let path = arguments[1]
        return path.hasPrefix("/") && isLocallyAvailablePDF(URL(fileURLWithPath: path))
    }
    let path: String
    let bundleIdentifier: String?
    if arguments.count == 1 {
        path = arguments[0]
        bundleIdentifier = nil
    } else if arguments.count == 3 && arguments[0] == "--bundle-id" && !arguments[1].isEmpty {
        bundleIdentifier = arguments[1]
        path = arguments[2]
    } else {
        return false
    }

    guard path.hasPrefix("/") else { return false }
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
        guard !isApplication,
              let appURL = resolveTargetApplication(bundleIdentifier: bundleIdentifier,
                                                    lookup: { workspace.urlForApplication(withBundleIdentifier: $0) }) else {
            return false
        }
        workspace.open([target], withApplicationAt: appURL, configuration: config) {
            application, error in
            completed.finish(application, error: error)
        }
        return completed.waitForCompletion()
    }
    if isApplication {
        workspace.openApplication(at: target, configuration: config) {
            application, error in
            completed.finish(application, error: error)
        }
        return completed.waitForCompletion()
    }
    return workspace.open(target)
}

guard launch(Array(CommandLine.arguments.dropFirst())) else {
    fputs("macOS could not open the approved item.\n", stderr)
    exit(EXIT_FAILURE)
}
