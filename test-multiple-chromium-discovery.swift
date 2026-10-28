import Foundation

// Exercise several Chromium-family applications in one isolated inventory.
// Fixture bundles are never registered with macOS or launched.
@main
struct MultipleChromiumDiscoveryTests {
    static func main() throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory.appendingPathComponent(
            "pdf-chromium-discovery-0155-" + UUID().uuidString, isDirectory: true)
        let system = root.appendingPathComponent("Applications", isDirectory: true)
        let user = root.appendingPathComponent("User/Applications", isDirectory: true)
        let custom = root.appendingPathComponent("External Browsers", isDirectory: true)
        for directory in [system, user, custom] {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        defer { try? fileManager.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-launch")

        func makeApp(
            in directory: URL, name: String, identifier: String,
            executable: Bool = true
        ) throws -> URL {
            let app = directory.appendingPathComponent(name + ".app", isDirectory: true)
            let binaries = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try fileManager.createDirectory(at: binaries, withIntermediateDirectories: true)
            let info: [String: String] = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "Browser",
                "CFBundlePackageType": "APPL",
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            let binary = binaries.appendingPathComponent("Browser")
            let shell = "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
            try shell.write(to: binary, atomically: true, encoding: .utf8)
            try fileManager.setAttributes(
                [.posixPermissions: executable ? 0o755 : 0o644],
                ofItemAtPath: binary.path)
            return app
        }

        let brave = try makeApp(in: system, name: "Brave Browser",
                                identifier: "com.brave.Browser")
        let chrome = try makeApp(in: system, name: "Google Chrome",
                                 identifier: "com.google.Chrome")
        let chromium = try makeApp(in: user, name: "Chromium",
                                   identifier: "org.chromium.Chromium")
        let edge = try makeApp(in: custom, name: "Microsoft Edge",
                               identifier: "com.microsoft.edgemac")
        let vivaldi = try makeApp(in: custom, name: "Vivaldi",
                                  identifier: "com.vivaldi.Vivaldi")
        _ = try makeApp(in: system, name: "Text Editor", identifier: "example.editor")
        _ = try makeApp(in: system, name: "Chrome Impostor",
                        identifier: "com.google.Chrome.fake")
        _ = try makeApp(in: system, name: "Broken Opera",
                        identifier: "com.operasoftware.Opera", executable: false)

        let expected = [
            InstalledBrowser(bundleIdentifier: "com.brave.Browser", path: brave.path),
            InstalledBrowser(bundleIdentifier: "com.google.Chrome", path: chrome.path),
            InstalledBrowser(bundleIdentifier: "org.chromium.Chromium", path: chromium.path),
            InstalledBrowser(bundleIdentifier: "com.microsoft.edgemac", path: edge.path),
            InstalledBrowser(bundleIdentifier: "com.vivaldi.Vivaldi", path: vivaldi.path),
        ].sorted { ($0.bundleIdentifier, $0.path) < ($1.bundleIdentifier, $1.path) }

        // Chrome and Edge occur in multiple discovery sources. Their actual
        // installed bundles must each appear exactly once, not overwrite peers.
        func discover() -> [InstalledBrowser] {
            discoverInstalledBrowsers(
                searchDirectories: [system, user],
                additionalApplications: [edge, vivaldi, edge],
                registeredApplications: [chrome, edge])
        }
        let detected = discover()
        precondition(detected == expected,
                     "Discover five distinct Chromium-based browsers, in stable order")
        precondition(Set(detected.map(\.bundleIdentifier)).count == expected.count,
                     "Different Chromium browser bundle IDs must remain distinct")
        let data = try JSONEncoder().encode(detected)
        let decoded = try JSONDecoder().decode([InstalledBrowser].self, from: data)
        precondition(decoded == expected, "Multi-browser JSON inventory must round-trip")
        precondition(!fileManager.fileExists(atPath: launchMarker.path),
                     "Browser discovery must never execute a discovered browser")

        // One broken installation cannot hide or replace healthy browsers.
        let executablePath = chromium.appendingPathComponent("Contents/MacOS/Browser")
        try fileManager.setAttributes(
            [.posixPermissions: 0o644], ofItemAtPath: executablePath.path)
        let withoutChromium = discover()
        precondition(withoutChromium == expected.filter {
            $0.bundleIdentifier != "org.chromium.Chromium"
        }, "Exclude only the unavailable Chromium installation")
        precondition(!fileManager.fileExists(atPath: launchMarker.path),
                     "Discovery must not launch browsers during validation")

        print("PASS: multiple Chromium browsers, deduplication, sorting, JSON and safety")
    }
}
