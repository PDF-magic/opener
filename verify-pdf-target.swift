import AppKit
import UniformTypeIdentifiers

// Compare the selected application to Launch Services' registered PDF handlers.
// A name, installed bundle, or generic browser category alone is not proof.
func targetSupportsPDF(application: URL?, registeredPDFHandlers: [URL]) -> Bool {
    guard let application = application,
          application.pathExtension.lowercased() == "app" else {
        return false
    }
    let target = application.standardizedFileURL.resolvingSymlinksInPath()
    return registeredPDFHandlers.contains {
        $0.standardizedFileURL.resolvingSymlinksInPath() == target
    }
}

// Firefox can render local PDFs but is not necessarily registered with
// Launch Services as a PDF handler. Permit this one known viewer only after
// verifying that the selected bundle is the installed, executable Firefox app.
// All other destinations must remain registered PDF handlers.
func verifiedFirefoxPDFViewer(bundleIdentifier: String, application: URL?) -> Bool {
    guard bundleIdentifier == "org.mozilla.firefox",
          let target = application?.standardizedFileURL.resolvingSymlinksInPath(),
          target.pathExtension.lowercased() == "app" else { return false }

    var isDirectory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: target.path, isDirectory: &isDirectory),
          isDirectory.boolValue,
          let bundle = Bundle(url: target),
          bundle.bundleIdentifier == bundleIdentifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return false }
    return true
}

func applicationSupportsPDF(bundleIdentifier: String) -> Bool {
    let workspace = NSWorkspace.shared
    let selected = workspace.urlForApplication(withBundleIdentifier: bundleIdentifier)
    return targetSupportsPDF(
        application: selected,
        registeredPDFHandlers: workspace.urlsForApplications(toOpen: UTType.pdf)
    ) || verifiedFirefoxPDFViewer(bundleIdentifier: bundleIdentifier, application: selected)
}

#if !PDF_TARGET_TESTING
@main
struct VerifyPDFTarget {
    static func main() {
        guard CommandLine.arguments.count == 2,
              !CommandLine.arguments[1].isEmpty,
              applicationSupportsPDF(bundleIdentifier: CommandLine.arguments[1]) else {
            // Intentionally omit application and document paths from diagnostics.
            fputs("The selected application could not be verified to open PDFs.\n", stderr)
            exit(1)
        }
    }
}
#endif
