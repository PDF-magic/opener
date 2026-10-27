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
        // Firefox's built-in PDF viewer may not advertise a PDF document type
        // to macOS Launch Services. Exercise its separately verified bundle
        // without requiring Firefox to be installed on the CI runner.
        let sandbox = FileManager.default.temporaryDirectory
            .appendingPathComponent("pdf-magic-firefox-\(UUID().uuidString)", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: sandbox, withIntermediateDirectories: true)
            defer { try? FileManager.default.removeItem(at: sandbox) }

            func makeBundle(_ name: String, identifier: String, executable: Bool = true) throws -> URL {
                let app = sandbox.appendingPathComponent(name + ".app", isDirectory: true)
                let bin = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
                try FileManager.default.createDirectory(at: bin, withIntermediateDirectories: true)
                let plist: [String: Any] = [
                    "CFBundleIdentifier": identifier,
                    "CFBundleExecutable": "firefox",
                    "CFBundlePackageType": "APPL",
                ]
                let data = try PropertyListSerialization.data(
                    fromPropertyList: plist, format: .xml, options: 0)
                try data.write(to: app.appendingPathComponent("Contents/Info.plist"))
                if executable {
                    let program = bin.appendingPathComponent("firefox")
                    try Data("#!/bin/sh\\nexit 0\\n".utf8).write(to: program)
                    try FileManager.default.setAttributes([.posixPermissions: 0o755],
                                                          ofItemAtPath: program.path)
                }
                return app
            }

            let firefox = try makeBundle("Firefox", identifier: "org.mozilla.firefox")
            let impostor = try makeBundle("Impostor", identifier: "com.example.not-firefox")
            let missingExecutable = try makeBundle(
                "Incomplete", identifier: "org.mozilla.firefox", executable: false)
            precondition(!targetSupportsPDF(application: firefox, registeredPDFHandlers: []),
                         "Firefox regression must exercise the nonregistered path")
            precondition(verifiedFirefoxPDFViewer(
                bundleIdentifier: "org.mozilla.firefox", application: firefox),
                         "An installed and executable Firefox must be accepted")
            precondition(!verifiedFirefoxPDFViewer(
                bundleIdentifier: "com.example.browser", application: firefox),
                         "Other browser IDs cannot inherit the Firefox exception")
            precondition(!verifiedFirefoxPDFViewer(
                bundleIdentifier: "org.mozilla.firefox", application: impostor),
                         "A mismatched bundle identity cannot launch as Firefox")
            precondition(!verifiedFirefoxPDFViewer(
                bundleIdentifier: "org.mozilla.firefox", application: missingExecutable),
                         "Firefox without an executable must be rejected")
            precondition(!verifiedFirefoxPDFViewer(
                bundleIdentifier: "org.mozilla.firefox", application: sandbox
                    .appendingPathComponent("Missing.app")),
                         "Missing Firefox installations must be rejected")
            precondition(!verifiedFirefoxPDFViewer(
                bundleIdentifier: "org.mozilla.firefox", application: nil),
                         "A missing Firefox lookup must be rejected")
            precondition(!verifiedFirefoxPDFViewer(
                bundleIdentifier: "org.mozilla.firefox", application: notAnApp),
                         "An arbitrary file cannot impersonate Firefox")
        } catch {
            fatalError("Unable to construct Firefox verifier fixtures: \(error)")
        }
        print("PASS: registered PDF handlers and verified Mozilla Firefox targets.")
    }
}
