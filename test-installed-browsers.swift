import Foundation

@main
struct InstalledBrowserDiscoveryTests {
    static func main() throws {
        let fileManager = FileManager.default
        let root = fileManager.temporaryDirectory
            .appendingPathComponent("pdf-browser-discovery-" + UUID().uuidString, isDirectory: true)
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? fileManager.removeItem(at: root) }

        let system = root.appendingPathComponent("System Applications", isDirectory: true)
        let home = root.appendingPathComponent("User", isDirectory: true)
        let userApplications = home.appendingPathComponent("Applications", isDirectory: true)
        let libraryApplications = home.appendingPathComponent("Library/Applications", isDirectory: true)
        let custom = root.appendingPathComponent("External Browsers", isDirectory: true)
        for directory in [system, userApplications, libraryApplications, custom] {
            try fileManager.createDirectory(at: directory, withIntermediateDirectories: true)
        }

        func makeApp(
            at directory: URL, name: String, identifier: String,
            schemes: [String] = [], executable: Bool = true
        ) throws -> URL {
            let app = directory.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try fileManager.createDirectory(at: macos, withIntermediateDirectories: true)
            var info: [String: Any] = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "Browser",
                "CFBundlePackageType": "APPL",
            ]
            if !schemes.isEmpty {
                info["CFBundleURLTypes"] = [["CFBundleURLSchemes": schemes]]
            }
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let program = macos.appendingPathComponent("Browser")
                try "#!/bin/sh\nexit 0\n".write(to: program, atomically: true, encoding: .utf8)
                try fileManager.setAttributes([.posixPermissions: 0o755],
                                              ofItemAtPath: program.path)
            }
            return app
        }

        let systemBrowser = try makeApp(at: system, name: "Brave", identifier: "com.brave.Browser")
        // Distinct on-disk installations may share the exact same bundle ID.
        // Inventory records physical copies by canonical path, not just ID.
        let alternateBrave = try makeApp(
            at: userApplications, name: "Brave Alternate", identifier: "com.brave.Browser")
        let alternateBraveAlias = root.appendingPathComponent("Brave Alias.app", isDirectory: true)
        try fileManager.createSymbolicLink(at: alternateBraveAlias, withDestinationURL: alternateBrave)
        let userBrowser = try makeApp(
            at: userApplications, name: "Custom Browser", identifier: "example.browser.user",
            schemes: ["HTTPS"])
        let libraryBrowser = try makeApp(
            at: libraryApplications, name: "Firefox", identifier: "org.mozilla.firefox")
        let customBrowser = try makeApp(
            at: custom, name: "Movable Browser", identifier: "example.browser.custom",
            schemes: ["http", "https"])
        let registeredCustom = try makeApp(
            at: custom, name: "Registered", identifier: "example.browser.registered")
        let brokenBrave = try makeApp(
            at: custom, name: "Unusable Brave", identifier: "com.brave.Browser",
            executable: false)
        _ = try makeApp(at: system, name: "Text Editor", identifier: "example.editor")
        _ = try makeApp(
            at: system, name: "Broken Browser", identifier: "com.google.Chrome", executable: false)
        _ = try makeApp(
            at: system, name: "Scan Gate", identifier: "local.studio.brave-pdf-opener",
            schemes: ["https"])

        let directories = browserSearchDirectories(systemApplications: system, homeDirectory: home)
        precondition(directories == [system, userApplications, libraryApplications])

        let inventory = discoverInstalledBrowsers(
            searchDirectories: directories,
            additionalApplications: [
                customBrowser, customBrowser, alternateBrave, alternateBraveAlias, brokenBrave,
            ],
            registeredApplications: [registeredCustom, systemBrowser, alternateBrave]
        )
        let paths = Set(inventory.map(\.path))
        precondition(paths == Set([
            systemBrowser.path, alternateBrave.path, userBrowser.path, libraryBrowser.path,
            customBrowser.path, registeredCustom.path
        ]), "System, user, explicitly custom and registered custom browsers must be detected")
        precondition(inventory.count == paths.count, "Duplicate candidate paths must collapse")
        let braveCopies = inventory.filter { $0.bundleIdentifier == "com.brave.Browser" }
        precondition(
            braveCopies.map(\.path) == [systemBrowser.path, alternateBrave.path].sorted(),
            "Separate Brave installations with one bundle ID must retain distinct paths"
        )
        precondition(!paths.contains(alternateBraveAlias.path),
                     "Symlink aliases and repeated source entries must not create extra copies")
        precondition(!paths.contains(brokenBrave.path),
                     "An unusable duplicate must not hide the valid installations")
        let reversedDiscovery = discoverInstalledBrowsers(
            searchDirectories: Array(directories.reversed()),
            additionalApplications: [
                alternateBraveAlias, alternateBrave, customBrowser, brokenBrave, customBrowser,
            ],
            registeredApplications: [alternateBrave, systemBrowser, registeredCustom]
        )
        precondition(reversedDiscovery == inventory,
                     "Duplicate installation ordering must not depend on discovery source order")
        precondition(inventory == inventory.sorted {
            ($0.bundleIdentifier, $0.path) < ($1.bundleIdentifier, $1.path)
        }, "Inventory must be deterministic")

        let withoutCustom = discoverInstalledBrowsers(searchDirectories: directories)
        precondition(!withoutCustom.contains { $0.path == customBrowser.path },
                     "Do not traverse arbitrary disks without explicit selection or registration")
        let customDirectory = discoverInstalledBrowsers(
            searchDirectories: directories + [custom])
        precondition(customDirectory.contains { $0.path == customBrowser.path },
                     "An explicitly supplied directory must discover custom installations")
        let absent = discoverInstalledBrowsers(
            searchDirectories: [root.appendingPathComponent("Missing")],
            additionalApplications: [root.appendingPathComponent("missing.app")])
        precondition(absent.isEmpty, "Missing installations must not be invented")

        // Removing one physical copy must leave the other selectable in the
        // discovered inventory, without changing preference files or launch policy.
        try fileManager.removeItem(
            at: alternateBrave.appendingPathComponent("Contents/MacOS/Browser"))
        let afterRemoval = discoverInstalledBrowsers(
            searchDirectories: directories,
            additionalApplications: [alternateBraveAlias, brokenBrave],
            registeredApplications: [systemBrowser, alternateBrave]
        )
        precondition(
            afterRemoval.filter { $0.bundleIdentifier == "com.brave.Browser" }
                .map(\.path) == [systemBrowser.path],
            "Removing one duplicate must not suppress the remaining healthy installation"
        )
        print("PASS: browser discovery in system, user and custom locations; distinct duplicate installations")
    }
}
