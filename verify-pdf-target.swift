import AppKit
import Security
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

// Safari can render local PDFs without advertising itself as a PDF document
// handler. Only the genuine Apple-signed Safari bundle may use this exception.
func appleSignedSafari(at application: URL) -> Bool {
    var code: SecStaticCode?
    var requirement: SecRequirement?
    guard SecStaticCodeCreateWithPath(application as CFURL, SecCSFlags(), &code) == errSecSuccess,
          let code = code,
          SecRequirementCreateWithString(
              "anchor apple and identifier \"com.apple.Safari\"" as CFString,
              SecCSFlags(), &requirement
          ) == errSecSuccess,
          let requirement = requirement else { return false }
    return SecStaticCodeCheckValidity(code, SecCSFlags(), requirement) == errSecSuccess
}

func trustedSafariPDFTarget(
    application: URL?,
    bundleIdentifier: String,
    verifySignature: (URL) -> Bool = appleSignedSafari
) -> Bool {
    guard bundleIdentifier == "com.apple.Safari",
          let application = application?.standardizedFileURL.resolvingSymlinksInPath(),
          application.pathExtension.lowercased() == "app",
          let bundle = Bundle(url: application),
          bundle.bundleIdentifier == bundleIdentifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return false }
    return verifySignature(application)
}

func applicationSupportsPDF(bundleIdentifier: String) -> Bool {
    let workspace = NSWorkspace.shared
    let application = workspace.urlForApplication(withBundleIdentifier: bundleIdentifier)
    return targetSupportsPDF(
        application: application,
        registeredPDFHandlers: workspace.urlsForApplications(toOpen: UTType.pdf)
    ) || trustedSafariPDFTarget(application: application, bundleIdentifier: bundleIdentifier)
}

#if !PDF_TARGET_TESTING
@main
struct VerifyPDFTarget {
    static func main() {
        guard CommandLine.arguments.count == 2,
              !CommandLine.arguments[1].isEmpty,
              applicationSupportsPDF(bundleIdentifier: CommandLine.arguments[1]) else {
            // Intentionally omit application and document paths from diagnostics.
            fputs("The selected application cannot be verified to open PDFs.\n", stderr)
            exit(1)
        }
    }
}
#endif
