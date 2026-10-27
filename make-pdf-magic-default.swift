import AppKit
import UniformTypeIdentifiers

private let openerIdentifier = "local.studio.brave-pdf-opener"

// This action is opt-in. Verify the installed scan-gate bundle rather than
// changing an association based only on its filename or an arbitrary app path.
func verifiedPDFMagicOpener(at application: URL, files: FileManager = .default) -> Bool {
    guard application.lastPathComponent == "PDF Magic Opener.app",
          (try? files.destinationOfSymbolicLink(atPath: application.path)) == nil,
          let attributes = try? files.attributesOfItem(atPath: application.path),
          attributes[.type] as? FileAttributeType == .typeDirectory,
          let bundle = Bundle(url: application),
          bundle.bundleIdentifier == openerIdentifier,
          let executable = bundle.executableURL,
          files.isExecutableFile(atPath: executable.path),
          let types = bundle.object(forInfoDictionaryKey: "CFBundleDocumentTypes")
              as? [[String: Any]] else { return false }

    return types.contains { declaration in
        (declaration["LSItemContentTypes"] as? [String])?.contains("com.adobe.pdf") == true
    }
}

// Inject the registration closure so tests can verify the user action without
// ever changing a CI runner's actual PDF association.
func requestPDFMagicDefault(
    application: URL,
    register: (URL, @escaping (Error?) -> Void) -> Void,
    completion: @escaping (Bool) -> Void
) {
    guard verifiedPDFMagicOpener(at: application) else {
        completion(false)
        return
    }
    register(application) { error in completion(error == nil) }
}

#if !PDF_DEFAULT_ACTION_TESTING
@main
struct MakePDFMagicDefault {
    static func main() {
        // A .command file is the only intended trigger; no document paths or
        // user-supplied app substitutions are accepted.
        guard CommandLine.arguments.count == 1 else {
            fputs("Run the installed Make PDF Magic Opener Default action.\n", stderr)
            exit(1)
        }
        let app = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Applications/PDF Magic Opener.app", isDirectory: true)
        requestPDFMagicDefault(
            application: app,
            register: { application, finish in
                NSWorkspace.shared.setDefaultApplication(
                    at: application, toOpen: UTType.pdf, completionHandler: finish)
            },
            completion: { success in
                if success {
                    print("PDF Magic Opener is now the default PDF application.")
                    exit(0)
                }
                fputs("Could not set PDF Magic Opener as the default. Verify the installation or use Finder's Get Info.\n", stderr)
                exit(1)
            }
        )
        RunLoop.main.run()
    }
}
#endif
