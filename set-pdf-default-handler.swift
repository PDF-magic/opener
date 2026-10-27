import AppKit
import CoreServices
import UniformTypeIdentifiers

// A successful setDefaultApplication callback is not sufficient: ensure
// Launch Services actually reports the requested application as the PDF handler.
// The injected lookup keeps regression tests read-only.
func pdfDefaultHandlerChangeVerified(
    application: URL,
    currentBundleIdentifier: () -> String? = {
        LSCopyDefaultRoleHandlerForContentType(UTType.pdf.identifier as CFString, .all)?
            .takeRetainedValue() as String?
    }
) -> Bool {
    guard let selectedIdentifier = Bundle(url: application)?.bundleIdentifier,
          !selectedIdentifier.isEmpty else { return false }
    return currentBundleIdentifier() == selectedIdentifier
}

#if !PDF_DEFAULT_HANDLER_TESTING
guard let brave = NSWorkspace.shared.urlForApplication(withBundleIdentifier: "com.brave.Browser") else {
    fputs("Brave Browser is not installed.\n", stderr)
    exit(1)
}

let handler = CommandLine.arguments.count > 1 ? URL(fileURLWithPath: CommandLine.arguments[1]) : brave
NSWorkspace.shared.setDefaultApplication(at: handler, toOpen: .pdf) { error in
    if let error = error {
        fputs("Could not set the PDF default handler: \(error.localizedDescription)\n", stderr)
        exit(1)
    }
    guard pdfDefaultHandlerChangeVerified(application: handler) else {
        fputs("Could not verify the macOS PDF default handler change.\n", stderr)
        exit(1)
    }
    print("PDF opening uses \(handler.lastPathComponent).")
    exit(0)
}
RunLoop.main.run()
#endif
