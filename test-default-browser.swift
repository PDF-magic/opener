import AppKit
import Foundation

@main
struct DefaultBrowserTests {
    static func main() throws {
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("opener-browser-lookup-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }

        func makeApp(_ name: String, id: String, executable: Bool = true) throws -> URL {
            let appURL = root.appendingPathComponent(name + ".app")
            let macos = appURL.appendingPathComponent("Contents/MacOS")
            try FileManager.default.createDirectory(at: macos, withIntermediateDirectories: true)
            let plist: [String: String] = [
                "CFBundleIdentifier": id,
                "CFBundleExecutable": "Browser",
                "CFBundlePackageType": "APPL"
            ]
            let data = try PropertyListSerialization.data(
                fromPropertyList: plist, format: .xml, options: 0)
            try data.write(to: appURL.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let binary = macos.appendingPathComponent("Browser")
                try Data("#!/bin/sh\nexit 0\n".utf8).write(to: binary)
                try FileManager.default.setAttributes(
                    [.posixPermissions: 0o755], ofItemAtPath: binary.path)
            }
            return appURL
        }

        let browser = try makeApp("Browser", id: "com.example.Browser")
        let opener = try makeApp("Opener", id: "local.studio.brave-pdf-opener")
        let missingExecutable = try makeApp(
            "MissingExecutable", id: "com.example.Missing", executable: false)
        let plainDirectory = root.appendingPathComponent("NotAnApp")
        try FileManager.default.createDirectory(
            at: plainDirectory, withIntermediateDirectories: true)

        func resolve(_ appURL: URL?) -> String? {
            systemDefaultBrowserBundleIdentifier(lookup: { url in
                precondition(url.scheme == "https")
                precondition(url.host == "example.invalid")
                return appURL
            })
        }

        precondition(resolve(browser) == "com.example.Browser")
        precondition(resolve(opener) == nil)
        precondition(resolve(missingExecutable) == nil)
        precondition(resolve(plainDirectory) == nil)
        precondition(resolve(root.appendingPathComponent("Absent.app")) == nil)
        precondition(resolve(nil) == nil)
        print("System default browser lookup and invalid-target checks passed")
    }
}
