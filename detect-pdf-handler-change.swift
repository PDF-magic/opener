import Foundation

// Compare Launch Services' current PDF association with the installed scan gate.
// The lookup is shared with identify-pdf-handler.swift; neither function changes
// a file association or a user's chosen post-scan browser.
enum PDFHandlerChange: Equatable {
    case unchanged
    case replaced(String)
    case unknown
}

let pdfMagicOpenerBundleIdentifier = "local.studio.brave-pdf-opener"

func detectPDFHandlerChange(
    expectedBundleIdentifier: String = pdfMagicOpenerBundleIdentifier,
    lookup: () -> String? = { registeredPDFHandlerBundleIdentifier() }
) -> PDFHandlerChange {
    guard let current = lookup() else { return .unknown }
    if current == expectedBundleIdentifier { return .unchanged }
    return .replaced(current)
}

#if !PDF_HANDLER_CHANGE_TESTING
@main
struct DetectPDFHandlerChange {
    static func main() {
        guard CommandLine.arguments.count == 1 else {
            fputs("Usage: detect-pdf-handler-change (no arguments).\n", stderr)
            exit(64)
        }
        switch detectPDFHandlerChange() {
        case .unchanged:
            print("PDF Magic Opener remains the default PDF handler.")
        case .replaced(let bundleIdentifier):
            print("Another application is now the default PDF handler: \(bundleIdentifier)")
            // A distinct exit code lets a caller detect a takeover without
            // mistaking a failed/unavailable lookup for an actual change.
            exit(2)
        case .unknown:
            fputs("The current default PDF handler could not be determined.\n", stderr)
            exit(1)
        }
    }
}
#endif
