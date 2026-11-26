import AppKit
import Foundation

// Resolve the browser associated with HTTPS, never the default PDF handler:
// PDF Magic Opener may itself be the macOS default PDF handler.
private let openerBundleIdentifier = "local.studio.brave-pdf-opener"
private let browserProbe = URL(string: "https://example.invalid/")!

func systemDefaultBrowserBundleIdentifier(
    lookup: (URL) -> URL? = { NSWorkspace.shared.urlForApplication(toOpen: $0) }
) -> String? {
    var isDirectory: ObjCBool = false
    guard let appURL = lookup(browserProbe)?.standardizedFileURL.resolvingSymlinksInPath(),
          appURL.pathExtension.lowercased() == "app",
          FileManager.default.fileExists(atPath: appURL.path, isDirectory: &isDirectory),
          isDirectory.boolValue,
          let app = Bundle(url: appURL),
          let identifier = app.bundleIdentifier,
          identifier != openerBundleIdentifier,
          let executable = app.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return nil }
    return identifier
}

#if !DEFAULT_BROWSER_TESTING
@main
struct ResolveDefaultBrowser {
    static func main() {
        guard CommandLine.arguments.count == 1,
              let identifier = systemDefaultBrowserBundleIdentifier() else {
            fputs("Cannot resolve an installed system default browser.\n", stderr)
            exit(EXIT_FAILURE)
        }
        print(identifier)
    }
}
#endif
