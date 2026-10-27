import Foundation

// All checks use synthetic app bundles and an injected Launch Services lookup.
// CI must never change the runner's real PDF default application.
@main
struct VerifyDefaultPDFHandlerTests {
    static func main() throws {
        let manager = FileManager.default
        let root = manager.temporaryDirectory.appendingPathComponent(
            "opener-pdf-handler-verify-" + UUID().uuidString, isDirectory: true)
        defer { try? manager.removeItem(at: root) }

        func makeApp(_ name: String, identifier: String?) throws -> URL {
            let app = root.appendingPathComponent(name + ".app", isDirectory: true)
            let contents = app.appendingPathComponent("Contents", isDirectory: true)
            try manager.createDirectory(at: contents, withIntermediateDirectories: true)
            var metadata: [String: Any] = [
                "CFBundlePackageType": "APPL",
                "CFBundleExecutable": "Stub",
            ]
            if let identifier = identifier {
                metadata["CFBundleIdentifier"] = identifier
            }
            let plist = try PropertyListSerialization.data(
                fromPropertyList: metadata, format: .xml, options: 0)
            try plist.write(to: contents.appendingPathComponent("Info.plist"))
            let macos = contents.appendingPathComponent("MacOS", isDirectory: true)
            try manager.createDirectory(at: macos, withIntermediateDirectories: true)
            let executable = macos.appendingPathComponent("Stub")
            try "#!/bin/sh\nexit 0\n".write(
                to: executable, atomically: true, encoding: .utf8)
            try manager.setAttributes(
                [.posixPermissions: 0o755], ofItemAtPath: executable.path)
            return app
        }

        let opener = try makeApp("PDF Magic Opener", identifier: "local.studio.brave-pdf-opener")
        let other = try makeApp("Other PDF App", identifier: "com.example.viewer")
        let anonymous = try makeApp("Unknown App", identifier: nil)
        var checks = 0

        precondition(pdfDefaultHandlerChangeVerified(application: opener) {
            checks += 1
            return "local.studio.brave-pdf-opener"
        }, "The exact requested PDF association must be accepted")
        precondition(checks == 1, "The registered association must be re-read")

        precondition(!pdfDefaultHandlerChangeVerified(application: opener) {
            "com.apple.Preview"
        }, "A successful callback with an unchanged PDF handler must fail")
        precondition(!pdfDefaultHandlerChangeVerified(application: opener) {
            "com.example.viewer"
        }, "The registration of another app must fail")
        precondition(!pdfDefaultHandlerChangeVerified(application: opener) {
            nil
        }, "An unreadable PDF association must fail")
        precondition(pdfDefaultHandlerChangeVerified(application: other) {
            "com.example.viewer"
        }, "An explicitly selected non-Brave app must be supported")

        let file = root.appendingPathComponent("not-an-app.pdf")
        try "PDF".write(to: file, atomically: true, encoding: .utf8)
        precondition(!pdfDefaultHandlerChangeVerified(application: file) {
            "com.example.viewer"
        }, "A non-application target cannot be verified")
        precondition(!pdfDefaultHandlerChangeVerified(application: anonymous) {
            "com.example.viewer"
        }, "An application without a bundle ID cannot be verified")
        print("PASS: PDF default handler registration must match the selected app")
    }
}
