import AppKit
import Foundation

@main
struct BrowserApplicationMetadataTests {
    static func main() throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory.appendingPathComponent(
            "opener-browser-metadata-" + UUID().uuidString, isDirectory: true)
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: root) }

        func makeApp(
            _ name: String,
            identifier: String = "com.example.Browser",
            displayName: String? = "Localized Browser",
            bundleName: String? = "Browser Core",
            shortVersion: String? = "12.3.4",
            buildVersion: String? = "567",
            executable: Bool = true
        ) throws -> URL {
            let app = root.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try fileManager.createDirectory(at: macos, withIntermediateDirectories: true)
            var info = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "Browser Engine",
                "CFBundlePackageType": "APPL"
            ]
            if let displayName = displayName { info["CFBundleDisplayName"] = displayName }
            if let bundleName = bundleName { info["CFBundleName"] = bundleName }
            if let shortVersion = shortVersion { info["CFBundleShortVersionString"] = shortVersion }
            if let buildVersion = buildVersion { info["CFBundleVersion"] = buildVersion }
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let path = macos.appendingPathComponent("Browser Engine")
                try "#!/bin/sh\nexit 0\n".write(to: path, atomically: true, encoding: .utf8)
                try fileManager.setAttributes([.posixPermissions: 0o755], atPath: path.path)
            }
            return app
        }

        let browser = try makeApp("Browser With Spaces")
        let customIcon = NSImage(size: NSSize(width: 32, height: 32))
        var iconRequests: [URL] = []
        let found = browserApplicationMetadata(at: browser) { url in
            iconRequests.append(url)
            return customIcon
        }
        precondition(found?.bundleIdentifier == "com.example.Browser")
        precondition(found?.bundleURL == browser)
        precondition(found?.name == "Localized Browser")
        precondition(found?.version == "12.3.4")
        precondition(found?.executableURL == browser.appendingPathComponent("Contents/MacOS/Browser Engine"))
        precondition(found?.icon === customIcon)
        precondition(iconRequests == [browser], "Look up the icon for the installed bundle")
        precondition(browserApplicationMetadata(at: browser)?.icon != nil,
                     "macOS must return an application icon or generic fallback")

        if let tool = ProcessInfo.processInfo.environment["BROWSER_METADATA_TOOL"] {
            func execute(_ path: String) throws -> (Int32, Data) {
                let process = Process()
                process.executableURL = URL(fileURLWithPath: tool)
                process.arguments = [path]
                let output = Pipe()
                process.standardOutput = output
                process.standardError = Pipe()
                try process.run()
                process.waitUntilExit()
                return (process.terminationStatus, output.fileHandleForReading.readDataToEndOfFile())
            }
            let (status, data) = try execute(browser.path)
            precondition(status == 0)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            precondition(json?["name"] as? String == "Localized Browser")
            precondition(json?["version"] as? String == "12.3.4")
            precondition(json?["executablePath"] as? String == found?.executableURL.path)
            precondition(json?["bundleIdentifier"] as? String == "com.example.Browser")
            precondition(!(json?["iconTIFFBase64"] as? String ?? "").isEmpty,
                         "CLI must retrieve actual icon data for the application")
            let (invalidStatus, invalidData) = try execute(root.appendingPathComponent("Gone.app").path)
            precondition(invalidStatus != 0 && invalidData.isEmpty)
        }

        let buildOnly = try makeApp("Build Only", displayName: nil,
                                    shortVersion: nil, buildVersion: "98")
        let buildInfo = browserApplicationMetadata(at: buildOnly, iconLookup: { _ in nil })
        precondition(buildInfo?.name == "Browser Core")
        precondition(buildInfo?.version == "98")
        precondition(buildInfo?.icon == nil, "Absent artwork must not hide valid metadata")

        let fallback = try makeApp("No Metadata", displayName: "  ",
                                   bundleName: "", shortVersion: " ", buildVersion: nil)
        let fallbackInfo = browserApplicationMetadata(at: fallback)
        precondition(fallbackInfo?.name == "No Metadata")
        precondition(fallbackInfo?.version == nil)

        let missingExecutable = try makeApp("Missing Executable", executable: false)
        precondition(browserApplicationMetadata(at: missingExecutable) == nil)
        let plain = root.appendingPathComponent("Not An App")
        try fileManager.createDirectory(at: plain, withIntermediateDirectories: true)
        precondition(browserApplicationMetadata(at: plain) == nil)
        precondition(browserApplicationMetadata(at: root.appendingPathComponent("Gone.app")) == nil)
        precondition(browserApplicationMetadata(at: URL(string: "https://example.invalid/Browser.app")!) == nil)

        // An executable symlink out of the app must not be returned as its location.
        let linkBundle = try makeApp("Linked Executable", executable: false)
        let externalExecutable = root.appendingPathComponent("outside-script")
        try "#!/bin/sh\n".write(to: externalExecutable, atomically: true, encoding: .utf8)
        try fileManager.setAttributes([.posixPermissions: 0o755], atPath: externalExecutable.path)
        try fileManager.createSymbolicLink(
            at: linkBundle.appendingPathComponent("Contents/MacOS/Browser Engine"),
            withDestinationURL: externalExecutable)
        precondition(browserApplicationMetadata(at: linkBundle) == nil,
                     "Executable paths must remain inside the installed bundle")
        print("PASS: browser names, icons, versions, executable paths, and invalid bundles")
    }
}
