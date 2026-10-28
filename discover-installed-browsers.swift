import Foundation
#if canImport(AppKit)
import AppKit
#endif

// Read-only browser inventory. This never selects a PDF destination or
// authorizes a browser to receive a scanned file.
struct InstalledBrowser: Codable, Equatable {
    let bundleIdentifier: String
    let path: String
}

private let knownBrowserIdentifiers: Set<String> = [
    "com.brave.Browser",
    "com.google.Chrome",
    "org.chromium.Chromium",
    "com.apple.Safari",
    "org.mozilla.firefox",
    "com.microsoft.edgemac",
    "company.thebrowser.Browser",
    "com.operasoftware.Opera",
    "com.vivaldi.Vivaldi",
]

func browserSearchDirectories(
    systemApplications: URL = URL(fileURLWithPath: "/Applications", isDirectory: true),
    homeDirectory: URL = FileManager.default.homeDirectoryForCurrentUser
) -> [URL] {
    [
        systemApplications,
        homeDirectory.appendingPathComponent("Applications", isDirectory: true),
        homeDirectory.appendingPathComponent("Library/Applications", isDirectory: true),
    ]
}

private func declaresWebURLScheme(_ bundle: Bundle) -> Bool {
    guard let types = bundle.infoDictionary?["CFBundleURLTypes"] as? [[String: Any]] else {
        return false
    }
    return types.contains { type in
        guard let schemes = type["CFBundleURLSchemes"] as? [String] else { return false }
        return schemes.contains { $0.lowercased() == "http" || $0.lowercased() == "https" }
    }
}

func discoverInstalledBrowsers(
    searchDirectories: [URL],
    additionalApplications: [URL] = [],
    registeredApplications: [URL] = [],
    fileManager: FileManager = .default
) -> [InstalledBrowser] {
    // Launch Services covers registered applications in arbitrary locations.
    // Explicit custom directories and paths cover unregistered installations.
    var candidates = additionalApplications + registeredApplications
    for directory in searchDirectories where directory.isFileURL {
        guard let contents = try? fileManager.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: [.isDirectoryKey],
            options: [.skipsHiddenFiles]
        ) else { continue }
        candidates += contents.filter { $0.pathExtension.lowercased() == "app" }
    }
    let registeredPaths = Set(registeredApplications.map {
        $0.standardizedFileURL.resolvingSymlinksInPath().path
    })
    var seen = Set<String>()
    var discovered = [InstalledBrowser]()
    for candidate in candidates where candidate.isFileURL {
        let application = candidate.standardizedFileURL.resolvingSymlinksInPath()
        guard application.pathExtension.lowercased() == "app",
              !seen.contains(application.path) else { continue }
        seen.insert(application.path)
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: application.path, isDirectory: &isDirectory),
              isDirectory.boolValue,
              let bundle = Bundle(url: application),
              let identifier = bundle.bundleIdentifier,
              identifier != "local.studio.brave-pdf-opener",
              let executable = bundle.executableURL,
              fileManager.isExecutableFile(atPath: executable.path) else { continue }

        // A bundle name or .app extension alone is not evidence of a browser.
        guard knownBrowserIdentifiers.contains(identifier)
                || registeredPaths.contains(application.path)
                || declaresWebURLScheme(bundle) else { continue }
        discovered.append(InstalledBrowser(bundleIdentifier: identifier, path: application.path))
    }
    return discovered.sorted {
        ($0.bundleIdentifier, $0.path) < ($1.bundleIdentifier, $1.path)
    }
}

#if canImport(AppKit)
func registeredBrowserApplications() -> [URL] {
    let workspace = NSWorkspace.shared
    let probe = URL(string: "https://example.invalid/")!
    var applications = workspace.urlsForApplications(toOpen: probe)
    for identifier in knownBrowserIdentifiers.sorted() {
        if let application = workspace.urlForApplication(withBundleIdentifier: identifier) {
            applications.append(application)
        }
    }
    return applications
}
#endif

#if !BROWSER_DISCOVERY_TESTING
@main
struct DiscoverInstalledBrowsers {
    static func main() {
        var directories = browserSearchDirectories()
        var applications = [URL]()
        let arguments = Array(CommandLine.arguments.dropFirst())
        var position = 0
        while position < arguments.count {
            guard position + 1 < arguments.count,
                  arguments[position] == "--search-directory"
                    || arguments[position] == "--application" else {
                fputs("Usage: discover-installed-browsers [--search-directory /absolute/path] [--application /absolute/path.app]\n", stderr)
                exit(EXIT_FAILURE)
            }
            let path = arguments[position + 1]
            guard path.hasPrefix("/") else {
                fputs("Application locations must be absolute paths.\n", stderr)
                exit(EXIT_FAILURE)
            }
            let url = URL(fileURLWithPath: path)
            if arguments[position] == "--application" {
                applications.append(url)
            } else {
                directories.append(url)
            }
            position += 2
        }
        #if canImport(AppKit)
        let registered = registeredBrowserApplications()
        #else
        let registered = [URL]()
        #endif
        let browsers = discoverInstalledBrowsers(
            searchDirectories: directories,
            additionalApplications: applications,
            registeredApplications: registered
        )
        guard let output = try? JSONEncoder().encode(browsers),
              let json = String(data: output, encoding: .utf8) else {
            fputs("Cannot encode installed browser inventory.\n", stderr)
            exit(EXIT_FAILURE)
        }
        print(json)
    }
}
#endif
