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
        print("PASS: registered PDF handlers and trusted Safari/Firefox exceptions.")
    }
}
