import AppKit
import Darwin
import Security
import UniformTypeIdentifiers

// Bundle caches Info.plist for a given URL even after an application is
// replaced in place. Do not use a cached identity to authorize a new bundle.
private func currentPDFTargetIdentity(at application: URL) -> (id: String, executable: String)? {
    let path = application.appendingPathComponent("Contents/Info.plist").path
    let descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
    guard descriptor >= 0 else { return nil }
    defer { close(descriptor) }

    let limit = 1024 * 1024
    var metadata = stat()
    guard fstat(descriptor, &metadata) == 0,
          (metadata.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          metadata.st_size > 0, metadata.st_size <= limit else { return nil }
    let file = FileHandle(fileDescriptor: descriptor, closeOnDealloc: false)
    guard let bytes = try? file.read(upToCount: limit + 1),
          !bytes.isEmpty, bytes.count <= limit,
          let raw = try? PropertyListSerialization.propertyList(
              from: bytes, options: [], format: nil),
          let info = raw as? [String: Any],
          let identifier = info["CFBundleIdentifier"] as? String, !identifier.isEmpty,
          let executable = info["CFBundleExecutable"] as? String, !executable.isEmpty
    else { return nil }
    return (identifier, executable)
}

// Launch Services may keep registrations for deleted, moved, or damaged apps.
// Validate each discovered bundle without opening it or changing preferences.
// Resolve symlinks to support real installations reached through aliases.
func verifiedDiscoveredApplication(
    at url: URL, expectedBundleIdentifier: String? = nil
) -> URL? {
    let target = url.standardizedFileURL.resolvingSymlinksInPath()
    guard target.isFileURL, target.pathExtension.lowercased() == "app" else {
        return nil
    }
    let files = FileManager.default
    var isDirectory: ObjCBool = false
    let info = target.appendingPathComponent("Contents/Info.plist")
    guard files.fileExists(atPath: target.path, isDirectory: &isDirectory),
          isDirectory.boolValue,
          files.isReadableFile(atPath: target.path),
          files.isReadableFile(atPath: info.path),
          (try? info.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true,
          let bundle = Bundle(url: target),
          let diskIdentity = currentPDFTargetIdentity(at: target),
          let identifier = bundle.bundleIdentifier, !identifier.isEmpty,
          diskIdentity.id == identifier,
          expectedBundleIdentifier == nil || identifier == expectedBundleIdentifier,
          let executable = bundle.executableURL?.resolvingSymlinksInPath(),
          diskIdentity.executable == executable.lastPathComponent,
          (try? executable.resourceValues(forKeys: [.isRegularFileKey]))?.isRegularFile == true,
          files.isExecutableFile(atPath: executable.path) else {
        return nil
    }
    return target
}

// Preserve discovery order and the user's installed-app choices while omitting
// entries for stale or unusable bundle paths.
func usableDiscoveredApplications(_ candidates: [URL]) -> [URL] {
    candidates.compactMap { verifiedDiscoveredApplication(at: $0) }
}

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

// Opera can view local PDFs even when macOS does not advertise its PDF
// registration. Restrict this exception to the genuine Opera-signed bundle.
func operaSignedPDFViewer(at application: URL) -> Bool {
    var code: SecStaticCode?
    var requirement: SecRequirement?
    guard SecStaticCodeCreateWithPath(application as CFURL, SecCSFlags(), &code) == errSecSuccess,
          let code = code,
          SecRequirementCreateWithString(
              "anchor apple generic and identifier \"com.operasoftware.Opera\" and certificate leaf[subject.OU] = \"A2P9LX4JPN\"" as CFString,
              SecCSFlags(), &requirement
          ) == errSecSuccess,
          let requirement = requirement else { return false }
    return SecStaticCodeCheckValidity(code, SecCSFlags(), requirement) == errSecSuccess
}

func trustedOperaPDFTarget(
    application: URL?,
    bundleIdentifier: String,
    verifySignature: (URL) -> Bool = operaSignedPDFViewer
) -> Bool {
    guard bundleIdentifier == "com.operasoftware.Opera",
          let target = application?.standardizedFileURL.resolvingSymlinksInPath(),
          target.pathExtension.lowercased() == "app",
          let bundle = Bundle(url: target),
          bundle.bundleIdentifier == bundleIdentifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return false }
    return verifySignature(target)
}

// Standard Firefox releases contain a PDF viewer even when Launch Services
// does not advertise PDF support. The exception requires Mozilla's actual
// Developer ID signature, not just a spoofable bundle identifier.
func mozillaSignedFirefox(at application: URL) -> Bool {
    var code: SecStaticCode?
    var requirement: SecRequirement?
    guard SecStaticCodeCreateWithPath(application as CFURL, SecCSFlags(), &code) == errSecSuccess,
          let code = code,
          SecRequirementCreateWithString(
              "anchor apple generic and identifier \"org.mozilla.firefox\" and certificate leaf[subject.OU] = \"43AQ936H96\"" as CFString,
              SecCSFlags(), &requirement
          ) == errSecSuccess,
          let requirement = requirement else { return false }
    return SecStaticCodeCheckValidity(code, SecCSFlags(), requirement) == errSecSuccess
}

func trustedFirefoxPDFTarget(
    application: URL?,
    bundleIdentifier: String,
    verifySignature: (URL) -> Bool = mozillaSignedFirefox
) -> Bool {
    guard bundleIdentifier == "org.mozilla.firefox",
          let application = application?.standardizedFileURL.resolvingSymlinksInPath(),
          application.pathExtension.lowercased() == "app",
          let bundle = Bundle(url: application),
          bundle.bundleIdentifier == bundleIdentifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return false }
    return verifySignature(application)
}

// Resolve the same ranked, verified installation as the native file launcher.
// Do not accept a different copy simply because it advertises PDF support.
func resolveVerifiedPDFApplication(
    bundleIdentifier: String,
    lookupAll: (String) -> [URL] = {
        NSWorkspace.shared.urlsForApplications(withBundleIdentifier: $0)
    }
) -> URL? {
    guard !bundleIdentifier.isEmpty,
          bundleIdentifier != "local.studio.brave-pdf-opener" else { return nil }
    let candidates = lookupAll(bundleIdentifier)
    // Launch Services ranks all registered copies by suitability. Skip stale
    // registrations, mismatched IDs, and nonexecutable bundles while retaining
    // that order; never substitute another browser or the PDF scan gate.
    for candidate in candidates {
        guard let target = verifiedDiscoveredApplication(
            at: candidate, expectedBundleIdentifier: bundleIdentifier
        ) else { continue }
        return target
    }
    return nil
}

func applicationSupportsPDF(bundleIdentifier: String) -> Bool {
    let workspace = NSWorkspace.shared
    let application = resolveVerifiedPDFApplication(bundleIdentifier: bundleIdentifier)
    return targetSupportsPDF(
        application: application,
        registeredPDFHandlers: usableDiscoveredApplications(
            workspace.urlsForApplications(toOpen: UTType.pdf)
        )
    ) || trustedSafariPDFTarget(application: application, bundleIdentifier: bundleIdentifier)
      || trustedArcPDFTarget(application: application, bundleIdentifier: bundleIdentifier)
      || verifiedVivaldiPDFViewer(bundleIdentifier: bundleIdentifier, application: application) ||
        trustedOperaPDFTarget(application: application, bundleIdentifier: bundleIdentifier)
      || trustedFirefoxPDFTarget(application: application, bundleIdentifier: bundleIdentifier)
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
