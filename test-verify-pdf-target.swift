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
        // The standard Opera app has a built-in PDF viewer but may not
        // advertise a PDF document type. This synthetic app is not signed.
        let opera = temporaryRoot.appendingPathComponent("Opera.app", isDirectory: true)
        let operaContents = opera.appendingPathComponent("Contents", isDirectory: true)
        let operaBin = operaContents.appendingPathComponent("MacOS", isDirectory: true)
        try! fileManager.createDirectory(at: operaBin, withIntermediateDirectories: true)
        let operaInfo: [String: Any] = [
            "CFBundleIdentifier": "com.operasoftware.Opera",
            "CFBundleExecutable": "Opera",
            "CFBundlePackageType": "APPL",
        ]
        let operaPlist = try! PropertyListSerialization.data(
            fromPropertyList: operaInfo, format: .xml, options: 0
        )
        try! operaPlist.write(to: operaContents.appendingPathComponent("Info.plist"))
        let operaExecutable = operaBin.appendingPathComponent("Opera")
        try! "#!/bin/sh\nexit 0\n".write(
            to: operaExecutable, atomically: true, encoding: .utf8
        )
        try! fileManager.setAttributes(
            [.posixPermissions: 0o755], ofItemAtPath: operaExecutable.path
        )
        precondition(trustedOperaPDFTarget(
            application: opera, bundleIdentifier: "com.operasoftware.Opera",
            verifySignature: { _ in true }
        ), "Genuine executable Opera should be eligible for its PDF exception")
        precondition(!trustedOperaPDFTarget(
            application: opera, bundleIdentifier: "com.operasoftware.Opera",
            verifySignature: { _ in false }
        ), "An untrusted Opera signature must be rejected")
        precondition(!operaSignedPDFViewer(at: opera),
                     "An unsigned Opera fixture must fail actual code-signing validation")
        precondition(!trustedOperaPDFTarget(
            application: opera, bundleIdentifier: "com.operasoftware.OperaGX",
            verifySignature: { _ in true }
        ), "Opera GX and other browsers must not inherit this exception")
        precondition(!trustedOperaPDFTarget(
            application: nil, bundleIdentifier: "com.operasoftware.Opera",
            verifySignature: { _ in true }
        ), "An uninstalled Opera must be rejected")
        precondition(!trustedOperaPDFTarget(
            application: notAnApp, bundleIdentifier: "com.operasoftware.Opera",
            verifySignature: { _ in true }
        ), "A non-application path must be rejected")
        try! fileManager.removeItem(at: operaExecutable)
        precondition(!trustedOperaPDFTarget(
            application: opera, bundleIdentifier: "com.operasoftware.Opera",
            verifySignature: { _ in true }
        ), "Opera without an executable must be rejected")
        print("PASS: PDF handlers and verified Safari/Opera exceptions.")
    }
}
