import Foundation

@main
struct PDFTargetVerificationTests {
    static func main() {
        let root = URL(fileURLWithPath: "/tmp/pdf-target-test")
        let pdfViewer = root.appendingPathComponent("PDF Viewer.app")
        let otherApp = root.appendingPathComponent("Other.app")
        let notAnApp = root.appendingPathComponent("document.pdf")
        let registered = [pdfViewer]

        precondition(targetSupportsPDF(application: pdfViewer,
                                       registeredPDFHandlers: registered),
                     "Registered PDF handler should be accepted")
        precondition(!targetSupportsPDF(application: otherApp,
                                        registeredPDFHandlers: registered),
                     "Unregistered application must be rejected")
        precondition(!targetSupportsPDF(application: nil,
                                        registeredPDFHandlers: registered),
                     "Missing target must be rejected")
        precondition(!targetSupportsPDF(application: notAnApp,
                                        registeredPDFHandlers: [notAnApp]),
                     "A non-application path must not be accepted")
        precondition(!targetSupportsPDF(application: pdfViewer,
                                        registeredPDFHandlers: []),
                     "No PDF registrations must fail closed")
        // Build unsigned fixtures to prove the Safari exception is both narrow
        // and dependent on a trusted signature.
        let fileManager = FileManager.default
        let temporaryRoot = fileManager.temporaryDirectory
            .appendingPathComponent("opener-safari-" + UUID().uuidString, isDirectory: true)
        defer { try? fileManager.removeItem(at: temporaryRoot) }
        let safari = temporaryRoot.appendingPathComponent("Safari.app", isDirectory: true)
        let contents = safari.appendingPathComponent("Contents", isDirectory: true)
        let macos = contents.appendingPathComponent("MacOS", isDirectory: true)
        try! fileManager.createDirectory(at: macos, withIntermediateDirectories: true)
        let info: [String: Any] = [
            "CFBundleIdentifier": "com.apple.Safari",
            "CFBundleExecutable": "Safari",
            "CFBundlePackageType": "APPL",
        ]
        let propertyList = try! PropertyListSerialization.data(
            fromPropertyList: info, format: .xml, options: 0
        )
        try! propertyList.write(to: contents.appendingPathComponent("Info.plist"))
        let executable = macos.appendingPathComponent("Safari")
        try! "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
        try! fileManager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)
        precondition(trustedSafariPDFTarget(
            application: safari, bundleIdentifier: "com.apple.Safari",
            verifySignature: { _ in true }
        ), "A properly identified, trusted Safari target must be allowed")
        precondition(!trustedSafariPDFTarget(
            application: safari, bundleIdentifier: "com.apple.Safari",
            verifySignature: { _ in false }
        ), "Unsigned Safari impersonators must be denied")
        precondition(!trustedSafariPDFTarget(
            application: safari, bundleIdentifier: "com.brave.Browser",
            verifySignature: { _ in true }
        ), "Other browsers must not inherit the Safari exception")
        precondition(!trustedSafariPDFTarget(
            application: nil, bundleIdentifier: "com.apple.Safari",
            verifySignature: { _ in true }
        ), "A missing Safari installation must be denied")
        precondition(!trustedSafariPDFTarget(
            application: notAnApp, bundleIdentifier: "com.apple.Safari",
            verifySignature: { _ in true }
        ), "A non-application path must be denied")
        try! fileManager.removeItem(at: executable)
        precondition(!trustedSafariPDFTarget(
            application: safari, bundleIdentifier: "com.apple.Safari",
            verifySignature: { _ in true }
        ), "Safari without an executable must be denied")
        // Arc is not necessarily registered as a PDF handler. Check only the
        // expected, executable and developer-signed Arc bundle is exempt.
        let arc = temporaryRoot.appendingPathComponent("Arc.app", isDirectory: true)
        let arcMacOS = arc.appendingPathComponent("Contents/MacOS", isDirectory: true)
        try! fileManager.createDirectory(at: arcMacOS, withIntermediateDirectories: true)
        let arcInfo: [String: Any] = [
            "CFBundleIdentifier": "company.thebrowser.Browser",
            "CFBundleExecutable": "Arc",
            "CFBundlePackageType": "APPL",
        ]
        let arcPlist = try! PropertyListSerialization.data(
            fromPropertyList: arcInfo, format: .xml, options: 0
        )
        try! arcPlist.write(to: arc.appendingPathComponent("Contents/Info.plist"))
        let arcExecutable = arcMacOS.appendingPathComponent("Arc")
        try! "#!/bin/sh\nexit 0\n".write(to: arcExecutable,
                                        atomically: true, encoding: .utf8)
        try! fileManager.setAttributes([.posixPermissions: 0o755],
                                       ofItemAtPath: arcExecutable.path)
        precondition(!targetSupportsPDF(application: arc, registeredPDFHandlers: []),
                     "Arc fixture must use the unregistered PDF path")
        precondition(trustedArcPDFTarget(
            application: arc, bundleIdentifier: "company.thebrowser.Browser",
            verifySignature: { _ in true }
        ), "Signed Arc with an executable should be allowed")
        precondition(!trustedArcPDFTarget(
            application: arc, bundleIdentifier: "company.thebrowser.Browser",
            verifySignature: { _ in false }
        ), "Unsigned Arc impostors must be rejected")
        precondition(!trustedArcPDFTarget(
            application: arc, bundleIdentifier: "com.brave.Browser",
            verifySignature: { _ in true }
        ), "Other browsers cannot inherit Arc's exception")
        precondition(!trustedArcPDFTarget(
            application: nil, bundleIdentifier: "company.thebrowser.Browser",
            verifySignature: { _ in true }
        ), "Missing Arc application must be rejected")
        precondition(!trustedArcPDFTarget(
            application: notAnApp, bundleIdentifier: "company.thebrowser.Browser",
            verifySignature: { _ in true }
        ), "A document must not impersonate Arc")
        let fakeArc = temporaryRoot.appendingPathComponent("FakeArc.app", isDirectory: true)
        let fakeMacOS = fakeArc.appendingPathComponent("Contents/MacOS", isDirectory: true)
        try! fileManager.createDirectory(at: fakeMacOS, withIntermediateDirectories: true)
        let fakeInfo: [String: Any] = [
            "CFBundleIdentifier": "com.example.fakeArc",
            "CFBundleExecutable": "Arc",
            "CFBundlePackageType": "APPL",
        ]
        let fakePlist = try! PropertyListSerialization.data(
            fromPropertyList: fakeInfo, format: .xml, options: 0
        )
        try! fakePlist.write(to: fakeArc.appendingPathComponent("Contents/Info.plist"))
        let fakeExecutable = fakeMacOS.appendingPathComponent("Arc")
        try! "#!/bin/sh\nexit 0\n".write(to: fakeExecutable,
                                        atomically: true, encoding: .utf8)
        try! fileManager.setAttributes([.posixPermissions: 0o755],
                                       ofItemAtPath: fakeExecutable.path)
        precondition(!trustedArcPDFTarget(
            application: fakeArc, bundleIdentifier: "company.thebrowser.Browser",
            verifySignature: { _ in true }
        ), "Mismatched Arc bundle identity must be rejected")
        try! fileManager.removeItem(at: arcExecutable)
        precondition(!trustedArcPDFTarget(
            application: arc, bundleIdentifier: "company.thebrowser.Browser",
            verifySignature: { _ in true }
        ), "Arc without an executable must be rejected")
        // Vivaldi can display PDFs without registering as the default handler.
        // These temporary bundles verify the exact identity/executable gate
        // without requiring Vivaldi to be installed on the CI machine.
        let vivaldiRoot = fileManager.temporaryDirectory
            .appendingPathComponent("opener-vivaldi-" + UUID().uuidString, isDirectory: true)
        defer { try? fileManager.removeItem(at: vivaldiRoot) }

        func makeVivaldiFixture(
            _ name: String, identifier: String, executable: Bool = true
        ) throws -> URL {
            let app = vivaldiRoot.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try fileManager.createDirectory(at: macos, withIntermediateDirectories: true)
            let info: [String: Any] = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "Vivaldi",
                "CFBundlePackageType": "APPL",
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let program = macos.appendingPathComponent("Vivaldi")
                try "#!/bin/sh\nexit 0\n".write(to: program, atomically: true, encoding: .utf8)
                try fileManager.setAttributes([.posixPermissions: 0o755],
                                              ofItemAtPath: program.path)
            }
            return app
        }

        do {
            let vivaldi = try makeVivaldiFixture("Vivaldi", identifier: "com.vivaldi.Vivaldi")
            let impostor = try makeVivaldiFixture("Impostor", identifier: "com.example.fake")
            let incomplete = try makeVivaldiFixture(
                "Incomplete", identifier: "com.vivaldi.Vivaldi", executable: false)
            precondition(verifiedVivaldiPDFViewer(
                bundleIdentifier: "com.vivaldi.Vivaldi", application: vivaldi),
                "Installed Vivaldi with its own bundle identity must be supported")
            precondition(!verifiedVivaldiPDFViewer(
                bundleIdentifier: "com.vivaldi.Vivaldi", application: impostor),
                "A different application must not impersonate Vivaldi")
            precondition(!verifiedVivaldiPDFViewer(
                bundleIdentifier: "com.brave.Browser", application: vivaldi),
                "No other browser may inherit the Vivaldi exception")
            precondition(!verifiedVivaldiPDFViewer(
                bundleIdentifier: "com.vivaldi.Vivaldi", application: incomplete),
                "Missing executable must fail closed")
            precondition(!verifiedVivaldiPDFViewer(
                bundleIdentifier: "com.vivaldi.Vivaldi", application: nil),
                "Missing application must fail closed")
            precondition(!verifiedVivaldiPDFViewer(
                bundleIdentifier: "com.vivaldi.Vivaldi", application: notAnApp),
                "Non-application paths must fail closed")
            precondition(!verifiedVivaldiPDFViewer(
                bundleIdentifier: "com.vivaldi.Vivaldi",
                application: vivaldiRoot.appendingPathComponent("Absent.app")),
                "Nonexistent applications must fail closed")
        } catch {
            fatalError("Could not build Vivaldi verification fixtures: \(error)")
        }
        print("PASS: verified Vivaldi PDF destination verification.")
        // A local Firefox fixture allows independent trust verification even
        // when Firefox is absent from the macOS CI runner.
        let firefox = temporaryRoot.appendingPathComponent("Firefox.app", isDirectory: true)
        let firefoxContents = firefox.appendingPathComponent("Contents", isDirectory: true)
        let firefoxBin = firefoxContents.appendingPathComponent("MacOS", isDirectory: true)
        try! fileManager.createDirectory(at: firefoxBin, withIntermediateDirectories: true)
        let firefoxInfo: [String: Any] = [
            "CFBundleIdentifier": "org.mozilla.firefox",
            "CFBundleExecutable": "firefox",
            "CFBundlePackageType": "APPL",
        ]
        let firefoxPlist = try! PropertyListSerialization.data(
            fromPropertyList: firefoxInfo, format: .xml, options: 0)
        try! firefoxPlist.write(to: firefoxContents.appendingPathComponent("Info.plist"))
        let firefoxExecutable = firefoxBin.appendingPathComponent("firefox")
        try! "#!/bin/sh\nexit 0\n".write(
            to: firefoxExecutable, atomically: true, encoding: .utf8)
        try! fileManager.setAttributes(
            [.posixPermissions: 0o755], ofItemAtPath: firefoxExecutable.path)
        precondition(!targetSupportsPDF(application: firefox, registeredPDFHandlers: []),
                     "Firefox should exercise the unregistered PDF handler path")
        precondition(trustedFirefoxPDFTarget(
            application: firefox, bundleIdentifier: "org.mozilla.firefox",
            verifySignature: { _ in true }
        ), "Verified Mozilla Firefox must be accepted")
        precondition(!trustedFirefoxPDFTarget(
            application: firefox, bundleIdentifier: "org.mozilla.firefox",
            verifySignature: { _ in false }
        ), "Unsigned Firefox impersonators must be denied")
        precondition(!trustedFirefoxPDFTarget(
            application: firefox, bundleIdentifier: "com.google.Chrome",
            verifySignature: { _ in true }
        ), "Chrome must not inherit the Firefox exception")
        precondition(!trustedFirefoxPDFTarget(
            application: safari, bundleIdentifier: "org.mozilla.firefox",
            verifySignature: { _ in true }
        ), "Different application identities must not be treated as Firefox")
        precondition(!trustedFirefoxPDFTarget(
            application: nil, bundleIdentifier: "org.mozilla.firefox",
            verifySignature: { _ in true }
        ), "Missing Firefox installations must be denied")
        precondition(!trustedFirefoxPDFTarget(
            application: notAnApp, bundleIdentifier: "org.mozilla.firefox",
            verifySignature: { _ in true }
        ), "Files cannot impersonate Firefox bundles")
        try! fileManager.removeItem(at: firefoxExecutable)
        precondition(!trustedFirefoxPDFTarget(
            application: firefox, bundleIdentifier: "org.mozilla.firefox",
            verifySignature: { _ in true }
        ), "Firefox without an executable must be denied")
        print("PASS: verified Arc PDF target and fail-closed impostor handling.")
        print("PASS: registered PDF handlers and verified Safari-only exception.")
    }
}
