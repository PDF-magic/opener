import AppKit
import Foundation

// opener-0161: exercise the real read-only discovery and preferences pipeline
// when Safari is the sole browser. Do not inspect the CI host's installed apps.
@main
struct NoThirdPartyBrowsersTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "pdf-no-third-party-0161-" + UUID().uuidString, isDirectory: true)
        let systemApps = root.appendingPathComponent("Applications", isDirectory: true)
        let home = root.appendingPathComponent("User", isDirectory: true)
        let userApps = home.appendingPathComponent("Applications", isDirectory: true)
        let libraryApps = home.appendingPathComponent("Library/Applications", isDirectory: true)
        for folder in [systemApps, userApps, libraryApps] {
            try files.createDirectory(at: folder, withIntermediateDirectories: true)
        }
        defer { try? files.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-launch")
        let savedTarget = root.appendingPathComponent("target-app.txt")
        let originalTarget = "org.example.previouslyChosenBrowser\n"
        try originalTarget.write(to: savedTarget, atomically: true, encoding: .utf8)

        func makeApp(_ name: String, id: String, directory: URL,
                     executable: Bool = true) throws -> URL {
            let app = directory.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let info: [String: String] = [
                "CFBundleIdentifier": id,
                "CFBundleExecutable": "Browser",
                "CFBundlePackageType": "APPL",
                "CFBundleDisplayName": name,
                "CFBundleShortVersionString": "26.0",
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let binary = macos.appendingPathComponent("Browser")
                try "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
                    .write(to: binary, atomically: true, encoding: .utf8)
                try files.setAttributes([.posixPermissions: 0o755],
                                        ofItemAtPath: binary.path)
            }
            return app
        }

        let safari = try makeApp("Safari", id: "com.apple.Safari", directory: systemApps)
        _ = try makeApp("Google Chrome", id: "org.example.lookalike",
                        directory: userApps)
        _ = try makeApp("Firefox", id: "org.mozilla.firefox",
                        directory: libraryApps, executable: false)
        let staleChrome = systemApps.appendingPathComponent(
            "Removed Chrome.app", isDirectory: true)
        let directories = browserSearchDirectories(
            systemApplications: systemApps, homeDirectory: home)
        let registered = [safari, staleChrome]

        func discover() -> [InstalledBrowser] {
            discoverInstalledBrowsers(
                searchDirectories: directories,
                additionalApplications: [],
                registeredApplications: registered)
        }
        func preferences() -> [BrowserPreferenceItem] {
            refreshedBrowserPreferenceItems(
                discover: discover,
                metadata: { url in
                    browserApplicationMetadata(at: url, iconLookup: { _ in nil })
                })
        }

        let expected = [InstalledBrowser(
            bundleIdentifier: "com.apple.Safari", path: safari.path)]
        precondition(discover() == expected,
                     "No third-party browsers: only installed Safari may be discovered")
        precondition(discover() == expected,
                     "Repeat discovery must not invent uninstalled browser choices")
        let encoded = try JSONEncoder().encode(discover())
        let decoded = try JSONDecoder().decode([InstalledBrowser].self, from: encoded)
        precondition(decoded == expected,
                     "Safari-only discovery must preserve the JSON inventory contract")
        let items = preferences()
        precondition(items.count == 1 && items[0].bundleIdentifier == "com.apple.Safari",
                     "Native preference list must display only Safari")
        precondition(items[0].name == "Safari" && items[0].version == "26.0",
                     "Displayed metadata must come from the real installed bundle")
        let list = BrowserPreferenceListView(items: items)
        precondition(list.rows.count == 1 && list.rows[0].nameField.stringValue == "Safari",
                     "Do not fabricate an Install Chrome or default third-party row")
        precondition(list.emptyState == nil, "Safari remains an available system browser")

        // Safari absent or unusable: there are no browsers, not a synthetic
        // Brave/Chrome fallback and not a reason to rewrite the saved target.
        let executable = safari.appendingPathComponent("Contents/MacOS/Browser")
        try files.setAttributes([.posixPermissions: 0o644],
                                ofItemAtPath: executable.path)
        precondition(discover().isEmpty, "Unusable Safari must not appear installed")
        precondition(preferences().isEmpty, "Unusable Safari cannot become a preference row")
        try files.removeItem(at: safari)
        precondition(discover().isEmpty, "Stale Safari registration must not produce a row")
        let emptyList = BrowserPreferenceListView(items: preferences())
        precondition(emptyList.rows.isEmpty &&
                     emptyList.emptyState?.heading.stringValue == "No browsers found",
                     "No-browser state must show guidance rather than a fake default")
        precondition(emptyList.emptyState?.preferenceNote.stringValue.contains(
            "has not changed") == true,
                     "Empty results must not suggest that the saved target was reset")
        let persistedTarget = try String(contentsOf: savedTarget, encoding: .utf8)
        precondition(persistedTarget == originalTarget,
                     "Discovery and display must not change saved custom browser choices")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Discovery and preferences must never execute an app")
        print("PASS: no third-party browsers, Safari-only and empty UI, preferences unchanged")
    }
}
