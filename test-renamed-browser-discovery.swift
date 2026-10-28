import Foundation

// opener-0160: exercise the real installed-browser discovery after an .app
// directory is renamed. No real browser, Launch Services registration,
// preferences, or scanned documents are involved.
@main
struct RenamedBrowserDiscoveryTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "pdf-renamed-browser-0160-" + UUID().uuidString, isDirectory: true)
        let applications = root.appendingPathComponent("Applications", isDirectory: true)
        try files.createDirectory(at: applications, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-browser-launch")

        func makeApp(name: String, identifier: String) throws -> URL {
            let app = applications.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let info: [String: String] = [
                "CFBundleIdentifier": identifier,
                "CFBundleName": "Brave",
                "CFBundleDisplayName": "Brave Browser",
                "CFBundleExecutable": "Browser",
                "CFBundlePackageType": "APPL",
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            let program = macos.appendingPathComponent("Browser")
            try "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
                .write(to: program, atomically: true, encoding: .utf8)
            try files.setAttributes(
                [.posixPermissions: 0o755], ofItemAtPath: program.path)
            return app
        }

        func inventory() -> [InstalledBrowser] {
            discoverInstalledBrowsers(
                searchDirectories: [applications],
                additionalApplications: [],
                registeredApplications: [])
        }

        let original = try makeApp(
            name: "Brave Browser", identifier: "com.brave.Browser")
        // A browser-like filename cannot qualify an unrelated app.
        let lookalike = try makeApp(
            name: "Lookalike Browser", identifier: "org.example.TextEditor")
        let expectedIdentifier = "com.brave.Browser"
        precondition(inventory() == [
            InstalledBrowser(bundleIdentifier: expectedIdentifier, path: original.path)
        ], "Initial discovery must use bundle identity, not app filename")

        let renamed = applications.appendingPathComponent(
            "My Renamed Browser ✨.app", isDirectory: true)
        try files.moveItem(at: original, to: renamed)
        precondition(!files.fileExists(atPath: original.path),
                     "Renaming must really remove the original path")

        let afterRename = inventory()
        precondition(afterRename == [
            InstalledBrowser(bundleIdentifier: expectedIdentifier, path: renamed.path)
        ], "Renamed .app must retain bundle identity and report its current path")
        precondition(!afterRename.contains { $0.path == original.path },
                     "Discovery must not keep a stale pre-rename path")
        precondition(inventory() == afterRename,
                     "Repeated discovery must remain stable after a rename")

        let encoded = try JSONEncoder().encode(afterRename)
        let decoded = try JSONDecoder().decode([InstalledBrowser].self, from: encoded)
        precondition(decoded == afterRename,
                     "Renamed application path must survive inventory JSON")

        // A bundle renamed to a non-.app extension no longer qualifies, even
        // though its Info.plist and executable still exist.
        let hidden = applications.appendingPathComponent(
            "My Renamed Browser ✨.disabled", isDirectory: true)
        try files.moveItem(at: renamed, to: hidden)
        precondition(inventory().isEmpty,
                     "Non-.app directory must not appear as a browser")

        try files.moveItem(at: hidden, to: renamed)
        precondition(inventory() == afterRename,
                     "Restoring .app extension must restore discovery")
        precondition(files.fileExists(atPath: lookalike.path),
                     "Unrelated installation must remain untouched")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Inventory must never launch the renamed app")

        print("PASS: renamed browser discovery tracks bundle identity and current path")
    }
}
