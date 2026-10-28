import Foundation

// An isolated Brave-only scenario for the actual installed-browser discovery
// implementation. Do not require Brave on CI or change real app registrations.
@main
struct BraveOnlyDiscoveryTests {
    static func main() throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory.appendingPathComponent(
            "pdf-brave-only-0153-" + UUID().uuidString, isDirectory: true)
        let applications = root.appendingPathComponent("Applications", isDirectory: true)
        try fileManager.createDirectory(at: applications, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-launch")

        func makeApplication(_ name: String, identifier: String) throws -> URL {
            let app = applications.appendingPathComponent(name + ".app", isDirectory: true)
            let executableDirectory = app.appendingPathComponent(
                "Contents/MacOS", isDirectory: true)
            try fileManager.createDirectory(
                at: executableDirectory, withIntermediateDirectories: true)
            let properties: [String: String] = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "Browser",
                "CFBundlePackageType": "APPL",
            ]
            let info = try PropertyListSerialization.data(
                fromPropertyList: properties, format: .xml, options: 0)
            try info.write(to: app.appendingPathComponent("Contents/Info.plist"))
            let executable = executableDirectory.appendingPathComponent("Browser")
            let script = "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
            try script.write(to: executable, atomically: true, encoding: .utf8)
            try fileManager.setAttributes(
                [.posixPermissions: 0o755], ofItemAtPath: executable.path)
            return app
        }

        let brave = try makeApplication(
            "Brave Browser", identifier: "com.brave.Browser")
        _ = try makeApplication("Text Editor", identifier: "example.editor")

        // Deliberately pass no macOS registrations or additional locations.
        // There is exactly one browser, Brave, in this isolated inventory.
        let detected = discoverInstalledBrowsers(
            searchDirectories: [applications],
            additionalApplications: [],
            registeredApplications: [])
        precondition(detected == [
            InstalledBrowser(bundleIdentifier: "com.brave.Browser", path: brave.path)
        ], "Brave must be the only discovered browser")
        let json = try JSONEncoder().encode(detected)
        let decoded = try JSONDecoder().decode([InstalledBrowser].self, from: json)
        precondition(decoded == detected, "Brave-only discovery must serialize correctly")
        precondition(!fileManager.fileExists(atPath: launchMarker.path),
                     "Discovery must not execute Brave or another application")

        // An invalid Brave installation must never appear as installed.
        let binary = brave.appendingPathComponent("Contents/MacOS/Browser")
        try fileManager.setAttributes(
            [.posixPermissions: 0o644], ofItemAtPath: binary.path)
        precondition(discoverInstalledBrowsers(searchDirectories: [applications]).isEmpty,
                     "A Brave bundle without an executable must not be discovered")
        precondition(!fileManager.fileExists(atPath: launchMarker.path),
                     "Failed discovery must not launch the application")

        print("PASS: Brave-only discovery, JSON, executable validation, no launch")
    }
}
