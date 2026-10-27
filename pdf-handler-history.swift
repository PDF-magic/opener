import AppKit
import CoreServices
import Darwin
import Foundation
import UniformTypeIdentifiers

private let openerPDFBundleIdentifier = "local.studio.brave-pdf-opener"

// Saved state contains only the prior bundle identifier, never PDF paths or data.
// Reject malformed identifiers rather than passing arbitrary text to Launch Services.
func validPreviousPDFBundleIdentifier(_ identifier: String) -> Bool {
    let bytes = Array(identifier.utf8)
    guard (3...255).contains(bytes.count),
          bytes.contains(46), !identifier.contains(".."),
          identifier != openerPDFBundleIdentifier else { return false }
    return bytes.enumerated().allSatisfy { index, byte in
        let alphaNumeric = (48...57).contains(byte) ||
            (65...90).contains(byte) || (97...122).contains(byte)
        return alphaNumeric || (index > 0 && (byte == 46 || byte == 45))
    }
}

func currentDefaultPDFBundleIdentifier() -> String? {
    guard let value = LSCopyDefaultRoleHandlerForContentType(
        UTType.pdf.identifier as CFString, .all
    )?.takeRetainedValue() as String?,
          !value.isEmpty else { return nil }
    return value
}

// Use a no-follow descriptor for stored state, not a path read susceptible to
// symlink substitution. Do not trust backups readable by other users.
func readPreviousPDFHandler(at path: String) -> String? {
    let fd = Darwin.open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)
    guard fd >= 0 else { return nil }
    defer { _ = Darwin.close(fd) }

    var status = stat()
    guard fstat(fd, &status) == 0,
          (status.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          (status.st_mode & mode_t(0o077)) == 0 else { return nil }

    var bytes = [UInt8](repeating: 0, count: 257)
    let count = bytes.withUnsafeMutableBytes { buffer in
        Darwin.read(fd, buffer.baseAddress, buffer.count)
    }
    guard count > 0, count <= 256,
          let raw = String(bytes: bytes.prefix(count), encoding: .ascii),
          raw.hasSuffix("\n") else { return nil }
    let identifier = String(raw.dropLast())
    return validPreviousPDFBundleIdentifier(identifier) ? identifier : nil
}

// Snapshot once, before the installer changes the association. Reinstallation
// must not replace the original handler with this app or a later user choice.
func recordPreviousPDFHandler(
    at path: String,
    current: () -> String? = currentDefaultPDFBundleIdentifier
) -> Bool {
    var status = stat()
    if lstat(path, &status) == 0 {
        return readPreviousPDFHandler(at: path) != nil
    }
    guard errno == ENOENT, let identifier = current() else { return false }
    if identifier == openerPDFBundleIdentifier {
        // An already-installed opener has no original association to recover.
        return true
    }
    guard validPreviousPDFBundleIdentifier(identifier) else { return false }

    let fd = Darwin.open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600))
    guard fd >= 0 else { return false }
    defer { _ = Darwin.close(fd) }

    let data = Array((identifier + "\n").utf8)
    let written = data.withUnsafeBytes { buffer -> Int in
        var offset = 0
        while offset < buffer.count {
            let count = Darwin.write(
                fd, buffer.baseAddress!.advanced(by: offset), buffer.count - offset)
            if count < 0 && errno == EINTR { continue }
            if count <= 0 { return -1 }
            offset += count
        }
        return offset
    }
    guard written == data.count, fsync(fd) == 0 else { return false }
    return true
}

// Restoration must never replace another application the user selected after
// installation. Validate the saved bundle against the installed app's identity.
func restorablePDFApplication(
    saved: String?,
    current: String?,
    resolve: (String) -> URL?
) -> URL? {
    guard current == openerPDFBundleIdentifier,
          let identifier = saved,
          validPreviousPDFBundleIdentifier(identifier),
          let app = resolve(identifier)?.standardizedFileURL.resolvingSymlinksInPath(),
          app.pathExtension.lowercased() == "app" else { return nil }

    var directory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: app.path, isDirectory: &directory),
          directory.boolValue,
          let bundle = Bundle(url: app),
          bundle.bundleIdentifier == identifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return nil }
    return app
}

#if !PDF_HANDLER_HISTORY_TESTING
@main
struct PDFHandlerHistory {
    static func main() {
        guard CommandLine.arguments.count == 3 else {
            fputs("Expected record or restore and a saved-handler file.\n", stderr)
            exit(EXIT_FAILURE)
        }
        let action = CommandLine.arguments[1]
        let path = CommandLine.arguments[2]
        switch action {
        case "record":
            guard recordPreviousPDFHandler(at: path) else {
                fputs("Cannot preserve the previous PDF handler; default unchanged.\n", stderr)
                exit(EXIT_FAILURE)
            }
            print("Previous PDF handler retained when one was available.")
        case "restore":
            let previous = readPreviousPDFHandler(at: path)
            guard let app = restorablePDFApplication(
                saved: previous,
                current: currentDefaultPDFBundleIdentifier(),
                resolve: { NSWorkspace.shared.urlForApplication(withBundleIdentifier: $0) }
            ) else {
                fputs("Cannot safely restore the previous PDF handler; default unchanged.\n", stderr)
                exit(EXIT_FAILURE)
            }
            NSWorkspace.shared.setDefaultApplication(at: app, toOpen: .pdf) { error in
                guard error == nil,
                      let expected = previous,
                      currentDefaultPDFBundleIdentifier() == expected else {
                    fputs("Could not verify the restored PDF handler.\n", stderr)
                    exit(EXIT_FAILURE)
                }
                print("Previous PDF handler restored.")
                exit(EXIT_SUCCESS)
            }
            RunLoop.main.run()
        default:
            fputs("Expected record or restore and a saved-handler file.\n", stderr)
            exit(EXIT_FAILURE)
        }
    }
}
#endif
