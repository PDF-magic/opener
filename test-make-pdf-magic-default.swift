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
            directory: String,
            bundleID: String = "local.studio.brave-pdf-opener",
            executable: Bool = true,
            pdfSupport: Bool = true
        ) throws -> URL {
            let app = root.appendingPathComponent(directory + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let plist: [String: Any] = [
                "CFBundleIdentifier": bundleID,
                "CFBundleExecutable": "PDFOpener",
                "CFBundlePackageType": "APPL",
                "CFBundleVersion": "1",
                "CFBundleDocumentTypes": [[
                    "CFBundleTypeRole": "Viewer",
                    "LSItemContentTypes": [pdfSupport ? "com.adobe.pdf" : "public.plain-text"],
                ]],
            ]
            let contents = try PropertyListSerialization.data(
                fromPropertyList: plist, format: .xml, options: 0)
            try contents.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let path = macos.appendingPathComponent("PDFOpener")
                try "#!/bin/sh\nexit 0\n".write(
                    to: path, atomically: true, encoding: .utf8)
                try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: path.path)
            }
            return app
        }

        let valid = try fixture(directory: "PDF Magic Opener")
        let wrongIdentity = try fixture(directory: "Elsewhere", bundleID: "com.example.app")
        let misleadingName = try fixture(
            directory: "PDF Magic Opener", bundleID: "com.example.spoof")
        // The last fixture shares a path. Create alternate fixtures under
        // separate directories so tests never mutate the valid bundle.
        let otherRoot = root.appendingPathComponent("other", isDirectory: true)
        try files.createDirectory(at: otherRoot, withIntermediateDirectories: true)
        let fake = otherRoot.appendingPathComponent("PDF Magic Opener.app", isDirectory: true)
        try files.copyItem(at: misleadingName, to: fake)
        // Restore the real fixture to its correct identity.
        let validPlist = valid.appendingPathComponent("Contents/Info.plist")
        let validInfo: [String: Any] = [
            "CFBundleIdentifier": "local.studio.brave-pdf-opener",
            "CFBundleExecutable": "PDFOpener",
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1",
            "CFBundleDocumentTypes": [[
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["com.adobe.pdf"],
            ]],
        ]
        try PropertyListSerialization.data(fromPropertyList: validInfo, format: .xml, options: 0)
            .write(to: validPlist)

        let noBinaryRoot = root.appendingPathComponent("missing-executable")
        try files.createDirectory(at: noBinaryRoot, withIntermediateDirectories: true)
        let absentExecutable = noBinaryRoot.appendingPathComponent("PDF Magic Opener.app")
        try files.copyItem(at: valid, to: absentExecutable)
        try files.removeItem(at: absentExecutable.appendingPathComponent("Contents/MacOS/PDFOpener"))

        let noPDFRoot = root.appendingPathComponent("not-pdf")
        try files.createDirectory(at: noPDFRoot, withIntermediateDirectories: true)
        let noPDF = noPDFRoot.appendingPathComponent("PDF Magic Opener.app")
        try files.copyItem(at: valid, to: noPDF)
        let textInfo = validInfo.merging([
            "CFBundleDocumentTypes": [[
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["public.plain-text"],
            ]]
        ]) { _, new in new }
        try PropertyListSerialization.data(fromPropertyList: textInfo, format: .xml, options: 0)
            .write(to: noPDF.appendingPathComponent("Contents/Info.plist"))

        let alias = root.appendingPathComponent("alias", isDirectory: true)
        try files.createDirectory(at: alias, withIntermediateDirectories: true)
        try files.createSymbolicLink(
            at: alias.appendingPathComponent("PDF Magic Opener.app"), withDestinationURL: valid)

        precondition(verifiedPDFMagicOpener(at: valid), "Real PDF Magic Opener should pass")
        for invalid in [wrongIdentity, fake, absentExecutable, noPDF,
                        alias.appendingPathComponent("PDF Magic Opener.app"),
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
            application: fake,
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
        print("PASS: explicit PDF default action validates the scan-gate bundle and reports errors.")
    }
}
