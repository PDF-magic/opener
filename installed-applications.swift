import Foundation

// Installed-application discovery is read-only. Do not select a target, change
// Launch Services associations, or open a file based on these search results.
struct InstalledApplication: Codable, Equatable {
    let name: String
    let bundleIdentifier: String
    let path: String
}

func decodeSpotlightPaths(_ output: Data) -> [String] {
    // mdfind -0 uses NUL separators, so newlines in filenames remain intact.
    output.split(separator: 0).compactMap { String(bytes: $0, encoding: .utf8) }
}

func matchingInstalledApplications(
    query: String,
    paths: [String],
    fileManager: FileManager = .default
) -> [InstalledApplication] {
    let search = query.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !search.isEmpty, search.count <= 256 else { return [] }

    var seenPaths = Set<String>()
    var matches: [InstalledApplication] = []
    for path in paths {
        guard path.hasPrefix("/") else { continue }
        let url = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
        guard url.pathExtension.lowercased() == "app" else { continue }
        var isDirectory: ObjCBool = false
        guard fileManager.fileExists(atPath: url.path, isDirectory: &isDirectory),
              isDirectory.boolValue,
              let bundle = Bundle(url: url),
              let identifier = bundle.bundleIdentifier,
              !identifier.isEmpty,
              let executable = bundle.executableURL,
              fileManager.isExecutableFile(atPath: executable.path) else { continue }

        let declaredName = (bundle.object(forInfoDictionaryKey: "CFBundleDisplayName") as? String)
            ?? (bundle.object(forInfoDictionaryKey: "CFBundleName") as? String)
        let name = (declaredName?.trimmingCharacters(in: .whitespacesAndNewlines))
            .flatMap { $0.isEmpty ? nil : $0 }
            ?? url.deletingPathExtension().lastPathComponent
        guard [name, identifier, url.deletingPathExtension().lastPathComponent]
            .contains(where: { $0.localizedCaseInsensitiveContains(search) }),
              seenPaths.insert(url.path).inserted else { continue }
        matches.append(InstalledApplication(name: name, bundleIdentifier: identifier, path: url.path))
    }
    return matches.sorted {
        let nameOrder = $0.name.localizedCaseInsensitiveCompare($1.name)
        if nameOrder != .orderedSame { return nameOrder == .orderedAscending }
        let identifierOrder = $0.bundleIdentifier.compare($1.bundleIdentifier)
        if identifierOrder != .orderedSame { return identifierOrder == .orderedAscending }
        return $0.path < $1.path
    }
}

enum ApplicationSearchError: Error {
    case unavailable
}

func spotlightApplicationPaths() throws -> [String] {
    // Ask macOS Spotlight for app bundles rather than walking private folders
    // or guessing that an app is installed from a known bundle identifier.
    let spotlight = URL(fileURLWithPath: "/usr/bin/mdfind")
    guard FileManager.default.isExecutableFile(atPath: spotlight.path) else {
        throw ApplicationSearchError.unavailable
    }
    let process = Process()
    process.executableURL = spotlight
    process.arguments = ["-0", "kMDItemContentTypeTree == 'com.apple.application-bundle'"]
    let output = Pipe()
    process.standardOutput = output
    process.standardError = FileHandle.nullDevice
    try process.run()
    let data = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else { throw ApplicationSearchError.unavailable }
    return decodeSpotlightPaths(data)
}

#if !INSTALLED_APPS_TESTING
@main
struct FindInstalledApplications {
    static func main() {
        guard CommandLine.arguments.count == 2,
              !CommandLine.arguments[1].trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              CommandLine.arguments[1].count <= 256 else {
            fputs("Usage: installed-applications <application-name-or-bundle-id>\n", stderr)
            exit(2)
        }
        do {
            let matches = matchingInstalledApplications(
                query: CommandLine.arguments[1], paths: try spotlightApplicationPaths()
            )
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.sortedKeys]
            let encoded = try encoder.encode(matches)
            print(String(decoding: encoded, as: UTF8.self))
        } catch {
            fputs("Could not query macOS for installed applications.\n", stderr)
            exit(1)
        }
    }
}
#endif
