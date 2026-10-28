import Foundation

// Safari-only discovery with synthetic app bundles; no dependency on the
// runner's installed browsers or changes to Launch Services or user settings.
@main
struct SafariOnlyDiscoveryTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "pdf-safari-only-0154-" + UUID().uuidString, isDirectory: true)
        let applications = root.appendingPathComponent("Applications", isDirectory: true)
        try files.createDirectory(at: applications, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-browser-launch")

        func makeApplication(_ name: String, identifier: String) throws -> URL {
            let application = applications.appendingPathComponent(
                name + ".app", isDirectory: true)
            let macos = application.appendingPathComponent(
                "Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let info: [String: String] = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "TestExecutable",
                "CFBundlePackageType": "APPL",
            ]
            let data = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try data.write(to: application.appendingPathComponent("Contents/Info.plist"))
            let executable = macos.appendingPathComponent("TestExecutable")
            let contents = "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
            try contents.write(to: executable, atomically: true, encoding: .utf8)
            try files.setAttributes(
                [.posixPermissions: 0o755], ofItemAtPath: executable.path)
            return application
        }

        // The directory has one supported browser even though it also contains
        // apps with browser-like names. No global registered browsers are read.
        let safari = try makeApplication(
            "Safari", identifier: "com.apple.Safari")
        _ = try makeApplication("Safari Lookalike", identifier: "org.example.notSafari")
        _ = try makeApplication("Notes", identifier: "org.example.editor")

        func inventory() -> [InstalledBrowser] {
            discoverInstalledBrowsers(
                searchDirectories: [applications],
                additionalApplications: [],
                registeredApplications: [])
        }

        let expected = [InstalledBrowser(
            bundleIdentifier: "com.apple.Safari", path: safari.path)]
        let found = inventory()
        precondition(found == expected,
                     "Safari must be the only browser discovered")
        precondition(inventory() == expected,
                     "Repeating Safari-only discovery must be deterministic")

        // The inventory's exact existing JSON contract must support a
        // Safari-only installation without fabricating another browser.
        let encoded = try JSONEncoder().encode(found)
        let decoded = try JSONDecoder().decode([InstalledBrowser].self, from: encoded)
        precondition(decoded == expected,
                     "Safari-only inventory must survive JSON serialization")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Discovery must never execute Safari or another app")

        // The same Safari-only system with a broken executable has no
        // discoverable browsers; it must not fall back to some other app.
        let executable = safari.appendingPathComponent(
            "Contents/MacOS/TestExecutable")
        try files.setAttributes(
            [.posixPermissions: 0o644], ofItemAtPath: executable.path)
        precondition(inventory().isEmpty,
                     "Safari without an executable must not appear as installed")
        try files.removeItem(at: safari)
        precondition(inventory().isEmpty,
                     "Removing Safari must leave no discovered browsers")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Discovery must not run application executables")

        print("PASS: Safari-only browser discovery, JSON contract and fail-closed handling")
    }
}
