import AppKit
import Darwin
import Foundation

// Read-only metadata for an already-discovered browser bundle. Browser identity,
// location discovery, and PDF-launch authorization are handled separately.
struct BrowserApplicationMetadata {
    let bundleIdentifier: String
    let bundleURL: URL
    let name: String
    let icon: NSImage?
    let version: String?
    let executableURL: URL
}

private func browserMetadataString(_ value: Any?) -> String? {
    guard let text = value as? String else { return nil }
    let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty,
          trimmed.count <= 256,
          !trimmed.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) })
    else { return nil }
    return trimmed
}

// Bundle caches Info.plist by URL. A browser upgraded at the same .app path
// may otherwise keep displaying its old version until the process restarts.
// Read only bounded, regular, non-symlinked metadata on each discovery pass.
private func currentBrowserInfo(at app: URL) -> [String: Any]? {
    let path = app.appendingPathComponent("Contents/Info.plist").path
    let descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
    guard descriptor >= 0 else { return nil }
    defer { close(descriptor) }

    var metadata = stat()
    let limit = 1024 * 1024
    guard fstat(descriptor, &metadata) == 0,
          (metadata.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          metadata.st_size > 0, metadata.st_size <= limit else { return nil }
    let handle = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
    guard let bytes = try? handle.read(upToCount: limit + 1),
          !bytes.isEmpty, bytes.count <= limit,
          let value = try? PropertyListSerialization.propertyList(
              from: bytes, options: [], format: nil),
          let info = value as? [String: Any] else { return nil }
    return info
}

func browserApplicationMetadata(
    at applicationURL: URL,
    iconLookup: (URL) -> NSImage? = { NSWorkspace.shared.icon(forFile: $0.path) }
) -> BrowserApplicationMetadata? {
    guard applicationURL.isFileURL else { return nil }
    let appURL = applicationURL.standardizedFileURL.resolvingSymlinksInPath()
    guard appURL.pathExtension.lowercased() == "app" else { return nil }

    var directory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: appURL.path, isDirectory: &directory),
          directory.boolValue,
          let bundle = Bundle(url: appURL),
          let info = currentBrowserInfo(at: appURL),
          let identifier = browserMetadataString(info["CFBundleIdentifier"]),
          identifier == bundle.bundleIdentifier,
          let executable = bundle.executableURL?.standardizedFileURL.resolvingSymlinksInPath(),
          FileManager.default.isExecutableFile(atPath: executable.path) else { return nil }

    // Never accept an Info.plist executable that redirects outside the bundle.
    let executableDirectory = appURL.appendingPathComponent("Contents/MacOS", isDirectory: true)
        .standardizedFileURL.resolvingSymlinksInPath()
    guard executable.deletingLastPathComponent() == executableDirectory else { return nil }

    // Keep localized app names where available, but do not let Bundle's
    // cached Info.plist override the newly installed version or raw name.
    let localized = bundle.localizedInfoDictionary
    let name = browserMetadataString(localized?["CFBundleDisplayName"])
        ?? browserMetadataString(info["CFBundleDisplayName"])
        ?? browserMetadataString(localized?["CFBundleName"])
        ?? browserMetadataString(info["CFBundleName"])
        ?? appURL.deletingPathExtension().lastPathComponent
    let version = browserMetadataString(info["CFBundleShortVersionString"])
        ?? browserMetadataString(info["CFBundleVersion"])

    return BrowserApplicationMetadata(
        bundleIdentifier: identifier,
        bundleURL: appURL,
        name: name,
        icon: iconLookup(appURL),
        version: version,
        executableURL: executable
    )
}

#if !BROWSER_METADATA_TESTING
@main
struct ReadBrowserApplicationMetadata {
    struct Output: Encodable {
        let bundleIdentifier: String
        let bundlePath: String
        let name: String
        let iconTIFFBase64: String?
        let version: String?
        let executablePath: String
    }

    static func main() {
        guard CommandLine.arguments.count == 2,
              let metadata = browserApplicationMetadata(
                  at: URL(fileURLWithPath: CommandLine.arguments[1])
              ) else {
            fputs("Expected an installed, executable application bundle.\n", stderr)
            exit(EXIT_FAILURE)
        }
        let output = Output(
            bundleIdentifier: metadata.bundleIdentifier,
            bundlePath: metadata.bundleURL.path,
            name: metadata.name,
            iconTIFFBase64: metadata.icon?.tiffRepresentation?.base64EncodedString(),
            version: metadata.version,
            executablePath: metadata.executableURL.path
        )
        guard let data = try? JSONEncoder().encode(output),
              let json = String(data: data, encoding: .utf8) else { exit(EXIT_FAILURE) }
        print(json)
    }
}
#endif
