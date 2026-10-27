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

// Arc displays PDFs through its built-in Chromium viewer even if macOS
// does not list it as a PDF document handler. Do not trust bundle names alone:
// verify the installed Arc executable and the Browser Company's signing team.
func browserCompanySignedArc(at application: URL) -> Bool {
    var code: SecStaticCode?
    var requirement: SecRequirement?
    guard SecStaticCodeCreateWithPath(application as CFURL, SecCSFlags(), &code) == errSecSuccess,
          let code = code,
          SecRequirementCreateWithString(
              "anchor apple generic and identifier \"company.thebrowser.Browser\" and certificate leaf[subject.OU] = \"S6N382Y83G\"" as CFString,
              SecCSFlags(), &requirement
          ) == errSecSuccess,
          let requirement = requirement else { return false }
    return SecStaticCodeCheckValidity(code, SecCSFlags(), requirement) == errSecSuccess
}

func trustedArcPDFTarget(
    application: URL?,
    bundleIdentifier: String,
    verifySignature: (URL) -> Bool = browserCompanySignedArc
) -> Bool {
    guard bundleIdentifier == "company.thebrowser.Browser",
          let application = application?.standardizedFileURL.resolvingSymlinksInPath(),
          application.pathExtension.lowercased() == "app",
          let bundle = Bundle(url: application),
          bundle.bundleIdentifier == bundleIdentifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return false }
    return verifySignature(application)
}

// Vivaldi's built-in PDF viewer may not be advertised as a macOS PDF handler.
// Only its exact, installed and executable application bundle can use this
// exception; all other unregistered apps remain blocked.
func verifiedVivaldiPDFViewer(bundleIdentifier: String, application: URL?) -> Bool {
    guard bundleIdentifier == "com.vivaldi.Vivaldi",
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
    let application = workspace.urlForApplication(withBundleIdentifier: bundleIdentifier)
    return targetSupportsPDF(
        application: application,
        registeredPDFHandlers: workspace.urlsForApplications(toOpen: UTType.pdf)
    ) || trustedSafariPDFTarget(application: application, bundleIdentifier: bundleIdentifier)
      || trustedArcPDFTarget(application: application, bundleIdentifier: bundleIdentifier)
      || verifiedVivaldiPDFViewer(bundleIdentifier: bundleIdentifier, application: application)
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
