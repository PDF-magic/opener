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

func applicationSupportsPDF(bundleIdentifier: String) -> Bool {
    let workspace = NSWorkspace.shared
    return targetSupportsPDF(
        application: workspace.urlForApplication(withBundleIdentifier: bundleIdentifier),
        registeredPDFHandlers: workspace.urlsForApplications(toOpen: UTType.pdf)
    )
}

#if !PDF_TARGET_TESTING
@main
struct VerifyPDFTarget {
    static func main() {
        guard CommandLine.arguments.count == 2,
              !CommandLine.arguments[1].isEmpty,
              applicationSupportsPDF(bundleIdentifier: CommandLine.arguments[1]) else {
            // Intentionally omit application and document paths from diagnostics.
            fputs("The selected application is not registered to open PDFs.\n", stderr)
            exit(1)
        }
    }
}
#endif
