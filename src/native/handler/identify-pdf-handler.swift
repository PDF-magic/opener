import CoreServices
import Foundation
import UniformTypeIdentifiers

// Inspect Launch Services' preferred *PDF* handler, not the HTTPS browser
// or the separate application configured to receive already-scanned PDFs.
// A PDF Magic Opener bundle ID is a valid answer when it owns the association.
func registeredPDFHandlerBundleIdentifier(
    lookup: (String) -> String? = { contentType in
        LSCopyDefaultRoleHandlerForContentType(contentType as CFString, .all)?
            .takeRetainedValue() as String?
    }
) -> String? {
    guard let bundleIdentifier = lookup(UTType.pdf.identifier),
          !bundleIdentifier.isEmpty,
          !bundleIdentifier.contains(where: { $0.isWhitespace || $0.isNewline }) else {
        return nil
    }
    return bundleIdentifier
}

#if !PDF_HANDLER_TESTING
@main
struct IdentifyPDFHandler {
    static func main() {
        guard CommandLine.arguments.count == 1,
              let identifier = registeredPDFHandlerBundleIdentifier() else {
            fputs("The macOS default PDF handler could not be identified.\n", stderr)
            exit(EXIT_FAILURE)
        }
        print(identifier)
    }
}
#endif
