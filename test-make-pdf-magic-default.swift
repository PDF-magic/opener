import Foundation

@main
struct PDFMagicDefaultActionTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "pdf-magic-default-action-" + UUID().uuidString, isDirectory: true)
        try files.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: root) }

        func fixture(
            folder: String,
            name: String = "PDF Magic Opener",
            bundleID: String = "local.studio.brave-pdf-opener",
            executable: Bool = true,
            pdfSupport: Bool = true
        ) throws -> URL {
            let app = root.appendingPathComponent(folder, isDirectory: true)
                .appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let info: [String: Any] = [
                "CFBundleIdentifier": bundleID,
                "CFBundleExecutable": "PDFOpener",
                "CFBundlePackageType": "APPL",
                "CFBundleVersion": "1",
                "CFBundleDocumentTypes": [[
                    "CFBundleTypeRole": "Viewer",
                    "LSItemContentTypes": [pdfSupport ? "com.adobe.pdf" : "public.plain-text"],
                ]],
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let bin = macos.appendingPathComponent("PDFOpener")
                try "#!/bin/sh\nexit 0\n".write(
                    to: bin, atomically: true, encoding: .utf8)
                try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: bin.path)
            }
            return app
        }

        let valid = try fixture(folder: "valid")
        let wrongName = try fixture(folder: "renamed", name: "Unrelated")
        let wrongID = try fixture(folder: "wrong-id", bundleID: "com.example.impostor")
        let missingExecutable = try fixture(folder: "no-executable", executable: false)
        let noPDF = try fixture(folder: "not-pdf", pdfSupport: false)
        let aliasRoot = root.appendingPathComponent("alias", isDirectory: true)
        try files.createDirectory(at: aliasRoot, withIntermediateDirectories: true)
        let alias = aliasRoot.appendingPathComponent("PDF Magic Opener.app", isDirectory: true)
        try files.createSymbolicLink(at: alias, withDestinationURL: valid)

        precondition(verifiedPDFMagicOpener(at: valid), "Real PDF Magic Opener should pass")
        for invalid in [wrongName, wrongID, missingExecutable, noPDF, alias,
                        root.appendingPathComponent("Missing.app")] {
            precondition(!verifiedPDFMagicOpener(at: invalid),
                         "Unverified bundles must not be registered as the PDF default")
        }

        var requests = 0
        var accepted: Bool?
        requestPDFMagicDefault(
            application: valid,
            register: { requested, finish in
                requests += 1
                precondition(requested == valid, "Only the verified opener may be registered")
                finish(nil)
            },
            completion: { accepted = $0 })
        precondition(requests == 1 && accepted == true, "Opt-in registration should succeed")

        requestPDFMagicDefault(
            application: wrongID,
            register: { _, _ in requests += 1 },
            completion: { accepted = $0 })
        precondition(requests == 1 && accepted == false, "Invalid apps must not change defaults")

        requestPDFMagicDefault(
            application: valid,
            register: { _, finish in
                requests += 1
                finish(NSError(domain: "PDFMagicDefaultTest", code: 1))
            },
            completion: { accepted = $0 })
        precondition(requests == 2 && accepted == false,
                     "Failure to register must be reported as failure")
        print("PASS: explicit PDF default action verifies its bundle and reports failures.")
    }
}
