import AppKit
import Foundation

// opener-1056: add a browser *after* the first discovery of an open
// preferences window. All applications and preferences are disposable;
// no PDF is opened and no actual Launch Services registration is changed.
@main
struct NewlyInstalledBrowserTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "newly-installed-browser-1056-" + UUID().uuidString, isDirectory: true)
        let systemApps = root.appendingPathComponent("Applications", isDirectory: true)
        let userApps = root.appendingPathComponent("Home/Applications", isDirectory: true)
        for directory in [systemApps, userApps] {
            try files.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        defer { try? files.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-launch")
        func install(_ name: String, id: String, version: String,
                     in directory: URL, executable: Bool) throws -> URL {
            let application = directory.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = application.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let info: [String: String] = [
                "CFBundleIdentifier": id,
                "CFBundleExecutable": "FixtureBrowser",
                "CFBundlePackageType": "APPL",
                "CFBundleDisplayName": name,
                "CFBundleShortVersionString": version,
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try plist.write(to: application.appendingPathComponent("Contents/Info.plist"))
            let binary = macos.appendingPathComponent("FixtureBrowser")
            try "#!/bin/sh\nprintf opened > \"\(launchMarker.path)\"\n"
                .write(to: binary, atomically: true, encoding: .utf8)
            try files.setAttributes(
                [.posixPermissions: executable ? 0o755 : 0o644], ofItemAtPath: binary.path)
            return application
        }

        let preferredID = "com.brave.Browser"
        let newID = "com.microsoft.edgemac"
        let brave = try install("Brave Browser", id: preferredID, version: "1.0",
                                in: systemApps, executable: true)
        let savedPreference = root.appendingPathComponent("target-app.txt")
        try (preferredID + "\n").write(to: savedPreference, atomically: true, encoding: .utf8)

        var scans = 0
        func discovered() -> [InstalledBrowser] {
            scans += 1
            return discoverInstalledBrowsers(
                searchDirectories: [systemApps, userApps], registeredApplications: [])
        }
        func items() -> [BrowserPreferenceItem] {
            refreshedBrowserPreferenceItems(
                discover: discovered,
                metadata: { browserApplicationMetadata(at: $0, iconLookup: { _ in nil }) })
        }

        let initial = items()
        precondition(initial.map(\.bundleIdentifier) == [preferredID],
                     "Only the original browser should be listed before installation")
        var visible = BrowserPreferenceListView(items: initial)
        var updates = 0
        let refresher = BrowserPreferenceLiveRefresher(
            initialItems: initial, discover: items,
            update: { refreshed in
                updates += 1
                visible = BrowserPreferenceListView(items: refreshed)
            })
        refresher.start(interval: 3600)
        guard let timer = refresher.timer, timer.isValid else {
            fatalError("The open preferences window must keep its discovery timer")
        }
        timer.fire()
        precondition(updates == 0, "No change must not rebuild the browser list")

        // A browser-like name with the wrong bundle ID must not be mistaken for Edge.
        _ = try install("Microsoft Edge Preview", id: "example.impostor",
                        version: "1.0", in: userApps, executable: true)
        timer.fire()
        precondition(updates == 0 && visible.rows.count == 1,
                     "Unrecognized applications must not appear as installed browsers")

        // A newly copied browser bundle is not installed until its executable
        // is usable. It must not appear during an incomplete installation.
        let edge = try install("Microsoft Edge", id: newID, version: "125.0",
                               in: userApps, executable: false)
        timer.fire()
        precondition(updates == 0 && discovered() == [
            InstalledBrowser(bundleIdentifier: preferredID, path: brave.path)
        ], "Incomplete browser installations must be ignored")

        let binary = edge.appendingPathComponent("Contents/MacOS/FixtureBrowser")
        try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: binary.path)
        timer.fire()
        precondition(updates == 1, "Installing a usable browser must refresh the open view")
        precondition(visible.rows.map(\.bundleIdentifier) == [preferredID, newID],
                     "The new Edge entry must join the existing Brave entry")
        guard let newRow = visible.rows.first(where: { $0.bundleIdentifier == newID }) else {
            fatalError("The installed browser must be visible")
        }
        precondition(newRow.nameField.stringValue == "Microsoft Edge"
                     && newRow.versionField?.stringValue == "Version 125.0",
                     "The new entry must use verified bundle metadata")
        precondition(discovered() == [
            InstalledBrowser(bundleIdentifier: preferredID, path: brave.path),
            InstalledBrowser(bundleIdentifier: newID, path: edge.path)
        ], "The new browser must be discovered at its actual user Applications path")
        precondition(!refresher.refreshIfChanged() && updates == 1,
                     "The next unchanged poll must not duplicate or reorder the new browser")

        // Discovery does not select or authorize a PDF destination. A target
        // still requires independent bundle and PDF-handler verification.
        precondition(resolveVerifiedPDFApplication(
            bundleIdentifier: newID, lookupAll: { _ in [edge] }) == edge)
        precondition(!targetSupportsPDF(application: edge, registeredPDFHandlers: []),
                     "Being newly installed alone cannot authorize PDF opening")
        precondition(targetSupportsPDF(application: edge, registeredPDFHandlers: [edge]),
                     "A separately verified, registered PDF handler can be eligible")
        let savedAfterInstall = try String(contentsOf: savedPreference, encoding: .utf8)
        precondition(savedAfterInstall == preferredID + "\n",
                     "Discovery must not switch or erase the existing user selection")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Neither discovery nor verification may execute a browser")

        refresher.stop()
        precondition(!timer.isValid && refresher.timer == nil)
        precondition(items().map(\.bundleIdentifier) == [preferredID, newID],
                     "A newly opened preferences window must independently see the install")
        precondition(scans >= 7, "Every poll must rediscover installed applications")
        print("PASS: newly installed browser appears safely without changing PDF preferences")
    }
}
