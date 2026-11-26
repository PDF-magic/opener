import AppKit
import Foundation
import UniformTypeIdentifiers

// Validate the exact selected bundle against the registered copy that the
// existing native launcher and PDF verifier will use. Do not register, open,
// or silently substitute another application.
func eligibleCustomBundleIdentifier(
    at candidate: URL,
    resolve: (String) -> URL? = { resolveVerifiedPDFApplication(bundleIdentifier: $0) },
    supportsPDF: (String) -> Bool = { applicationSupportsPDF(bundleIdentifier: $0) }
) -> String? {
    guard candidate.isFileURL,
          let selected = verifiedDiscoveredApplication(at: candidate),
          let identifier = Bundle(url: selected)?.bundleIdentifier,
          identifier.range(
              of: "^[A-Za-z0-9][A-Za-z0-9.-]{1,254}$",
              options: .regularExpression
          ) != nil,
          identifier.contains("."),
          !identifier.contains(".."),
          identifier != "local.studio.brave-pdf-opener",
          let resolved = resolve(identifier)?.standardizedFileURL.resolvingSymlinksInPath(),
          resolved == selected,
          supportsPDF(identifier) else { return nil }
    return identifier
}

#if !CUSTOM_APP_SELECTION_TESTING
@main
struct SelectCustomPDFApplication {
    static func main() {
        let arguments = Array(CommandLine.arguments.dropFirst())
        let selected: URL
        if arguments.isEmpty {
            let panel = NSOpenPanel()
            panel.title = "Select a PDF application"
            panel.message = "Choose an installed application to open scanned PDFs."
            panel.allowedContentTypes = [.applicationBundle]
            panel.canChooseFiles = true
            panel.canChooseDirectories = false
            panel.allowsMultipleSelection = false
            guard panel.runModal() == .OK, let chosen = panel.url else {
                // Cancellation is not a preference change.
                exit(EXIT_FAILURE)
            }
            selected = chosen
        } else if arguments.count == 2 && arguments[0] == "--application",
                  arguments[1].hasPrefix("/") {
            selected = URL(fileURLWithPath: arguments[1])
        } else {
            fputs("Use --application with an absolute .app path or omit it to choose interactively.\n", stderr)
            exit(EXIT_FAILURE)
        }
        guard let identifier = eligibleCustomBundleIdentifier(at: selected) else {
            fputs("The selected application is not an installed, registered PDF-capable destination.\n", stderr)
            exit(EXIT_FAILURE)
        }
        print(identifier)
    }
}
#endif
