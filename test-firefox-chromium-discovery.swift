import Foundation

// opener-0156: exercise the real discovery routine with Firefox and Chromium
// installed together. Disposable bundles avoid relying on the CI host's apps
// or modifying Launch Services, browser preferences, or the scanner.
@main
struct FirefoxChromiumDiscoveryTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "pdf-firefox-chromium-0156-" + UUID().uuidString, isDirectory: true)
        let system = root.appendingPathComponent("Applications", isDirectory: true)
        let home = root.appendingPathComponent("User", isDirectory: true)
        let userApps = home.appendingPathComponent("Applications", isDirectory: true)
        try files.createDirectory(at: system, withIntermediateDirectories: true)
        try files.createDirectory(at: userApps, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-launch")

        func makeApp(_ name: String, id: String, in directory: URL) throws -> URL {
            let app = directory.appendingPathComponent(name + ".app", isDirectory: true)
            let executableFolder = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: executableFolder, withIntermediateDirectories: true)
            let plist = try PropertyListSerialization.data(
                fromPropertyList: [
                    "CFBundleIdentifier": id,
                    "CFBundleExecutable": "Browser",
                    "CFBundlePackageType": "APPL",
                ], format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            let executable = executableFolder.appendingPathComponent("Browser")
            try "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n".write(
                to: executable, atomically: true, encoding: .utf8)
            try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)
            return app
        }

        let firefox = try makeApp(
            "Firefox", id: "org.mozilla.firefox", in: system)
        let chromium = try makeApp(
            "Chromium", id: "org.chromium.Chromium", in: userApps)
        _ = try makeApp("Firefox Copycat", id: "org.example.editor", in: system)
        _ = try makeApp("Chromium Copycat", id: "org.example.impostor", in: userApps)

        let directories = browserSearchDirectories(
            systemApplications: system, homeDirectory: home)
        precondition(directories == [system, userApps,
            home.appendingPathComponent("Library/Applications", isDirectory: true)])

        // Both browsers must remain distinct, regardless of the arrival order
        // or duplicate registrations of the same installed application.
        let expected = [
            InstalledBrowser(bundleIdentifier: "org.chromium.Chromium", path: chromium.path),
            InstalledBrowser(bundleIdentifier: "org.mozilla.firefox", path: firefox.path),
        ]
        func discover() -> [InstalledBrowser] {
            discoverInstalledBrowsers(
                searchDirectories: directories,
                additionalApplications: [firefox, chromium],
                registeredApplications: [chromium, firefox, chromium])
        }
        let together = discover()
        precondition(together == expected,
                     "Firefox and Chromium must both appear exactly once with their own paths")
        precondition(discover() == expected,
                     "Mixed-browser discovery must have deterministic ordering")
        let encoded = try JSONEncoder().encode(together)
        let roundTrip = try JSONDecoder().decode([InstalledBrowser].self, from: encoded)
        precondition(roundTrip == expected, "Both browser identities must survive JSON output")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Browser discovery must never launch Firefox, Chromium, or an impostor")

        // A removal must not hide or substitute the other installed browser,
        // even when Launch Services still reports the removed application's URL.
        try files.removeItem(at: firefox)
        precondition(discover() == [expected[0]],
                     "Removing Firefox must leave Chromium independently discoverable")
        precondition(!files.fileExists(atPath: launchMarker.path))

        // Reinstall Firefox and remove Chromium to exercise the opposite case.
        _ = try makeApp("Firefox", id: "org.mozilla.firefox", in: system)
        try files.removeItem(at: chromium)
        precondition(discover() == [expected[1]],
                     "Removing Chromium must leave Firefox independently discoverable")

        // A corrupted Firefox executable is not a valid remaining browser.
        let firefoxExecutable = firefox.appendingPathComponent("Contents/MacOS/Browser")
        try files.setAttributes([.posixPermissions: 0o644],
                                ofItemAtPath: firefoxExecutable.path)
        precondition(discover().isEmpty,
                     "Invalid and removed browsers must not become phantom choices")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Neither successful nor failed discovery may run application code")
        print("PASS: Firefox and Chromium together, independent removals, JSON, no app launch")
    }
}
