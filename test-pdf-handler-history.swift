import Foundation

@main
struct PDFHandlerHistoryTests {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory
            .appendingPathComponent("pdf-handler-history-" + UUID().uuidString, isDirectory: true)
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: root) }

        let stored = root.appendingPathComponent("previous-pdf-handler.txt")
        var lookups = 0
        precondition(recordPreviousPDFHandler(at: stored.path, current: {
            lookups += 1
            return "com.apple.Preview"
        }), "Initial installation must capture the registered PDF handler")
        precondition(lookups == 1)
        precondition(readPreviousPDFHandler(at: stored.path) == "com.apple.Preview")
        let permissions = try fm.attributesOfItem(atPath: stored.path)[.posixPermissions] as! NSNumber
        precondition(permissions.intValue & 0o777 == 0o600,
                     "Saved state must be private")

        precondition(recordPreviousPDFHandler(at: stored.path, current: {
            lookups += 1
            return "local.studio.brave-pdf-opener"
        }), "Reinstall must preserve the original handler")
        precondition(lookups == 1,
                     "Reinstall must not consult or replace a valid saved choice")
        precondition(readPreviousPDFHandler(at: stored.path) == "com.apple.Preview")

        let alreadyOpener = root.appendingPathComponent("already-opener.txt")
        precondition(recordPreviousPDFHandler(at: alreadyOpener.path, current: {
            "local.studio.brave-pdf-opener"
        }), "An already-installed opener must be accepted")
        precondition(!fm.fileExists(atPath: alreadyOpener.path),
                     "Do not save the opener as its own previous handler")
        let unknown = root.appendingPathComponent("unknown.txt")
        precondition(!recordPreviousPDFHandler(at: unknown.path, current: { nil }),
                     "Unknown previous handler must stop an association change")
        precondition(!fm.fileExists(atPath: unknown.path))

        let victim = root.appendingPathComponent("unrelated.txt")
        try "UNTOUCHED".write(to: victim, atomically: true, encoding: .utf8)
        let link = root.appendingPathComponent("symlink.txt")
        try fm.createSymbolicLink(at: link, withDestinationURL: victim)
        precondition(!recordPreviousPDFHandler(at: link.path, current: {
            "com.apple.Preview"
        }), "A symlink must not count as a saved preference")
        precondition(readPreviousPDFHandler(at: link.path) == nil,
                     "Stored state must not be read through a symlink")
        let victimContents = try String(contentsOf: victim, encoding: .utf8)
        precondition(victimContents == "UNTOUCHED",
                     "Unrelated files must not be overwritten")

        let invalid = root.appendingPathComponent("invalid.txt")
        for content in ["", "unqualified\n", "com..bad\n", "local.studio.brave-pdf-opener\n",
                        "com.apple.Preview\nanother\n", "com.apple.Preview"] {
            try content.write(to: invalid, atomically: true, encoding: .ascii)
            try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: invalid.path)
            precondition(readPreviousPDFHandler(at: invalid.path) == nil,
                         "Malformed saved preferences must fail closed")
            precondition(!recordPreviousPDFHandler(at: invalid.path, current: {
                "com.apple.Preview"
            }), "An existing invalid file must not be replaced")
        }
        try "com.apple.Preview\n".write(to: invalid, atomically: true, encoding: .ascii)
        try fm.setAttributes([.posixPermissions: 0o644], ofItemAtPath: invalid.path)
        precondition(readPreviousPDFHandler(at: invalid.path) == nil,
                     "World-readable backups must be refused")

        func makeApp(_ name: String, identifier: String, executable: Bool = true) throws -> URL {
            let app = root.appendingPathComponent(name + ".app", isDirectory: true)
            let bin = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try fm.createDirectory(at: bin, withIntermediateDirectories: true)
            let info: [String: Any] = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "Viewer",
                "CFBundlePackageType": "APPL",
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let binary = bin.appendingPathComponent("Viewer")
                try Data("#!/bin/sh\nexit 0\n".utf8).write(to: binary)
                try fm.setAttributes([.posixPermissions: 0o755], ofItemAtPath: binary.path)
            }
            return app
        }

        let preview = try makeApp("Preview", identifier: "com.apple.Preview")
        let impostor = try makeApp("Impostor", identifier: "com.example.other")
        let incomplete = try makeApp("Incomplete", identifier: "com.apple.Preview", executable: false)
        let openerID = "local.studio.brave-pdf-opener"
        let restore = restorablePDFApplication(
            saved: readPreviousPDFHandler(at: stored.path),
            current: openerID,
            resolve: { $0 == "com.apple.Preview" ? preview : nil }
        )
        precondition(restore == preview.standardizedFileURL,
                     "An existing verified original reader must be restorable")
        precondition(restorablePDFApplication(
            saved: "com.apple.Preview", current: "com.example.newchoice", resolve: { _ in preview }
        ) == nil, "Never overwrite a subsequent user-selected handler")
        precondition(restorablePDFApplication(
            saved: nil, current: openerID, resolve: { _ in preview }
        ) == nil, "A missing backup must not be guessed")
        precondition(restorablePDFApplication(
            saved: openerID, current: openerID, resolve: { _ in preview }
        ) == nil, "Never restore the scan gate to itself")
        precondition(restorablePDFApplication(
            saved: "com.apple.Preview", current: openerID, resolve: { _ in nil }
        ) == nil, "An uninstalled previous reader must fail closed")
        precondition(restorablePDFApplication(
            saved: "com.apple.Preview", current: openerID, resolve: { _ in impostor }
        ) == nil, "An impersonating bundle must fail closed")
        precondition(restorablePDFApplication(
            saved: "com.apple.Preview", current: openerID, resolve: { _ in incomplete }
        ) == nil, "Missing app executables must fail closed")

        print("PASS: private once-only PDF handler backup and explicit safe restoration.")
    }
}
