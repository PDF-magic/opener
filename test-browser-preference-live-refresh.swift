import AppKit
import Foundation

@main
struct BrowserPreferenceLiveRefreshTests {
    static func main() throws {
        func make(_ id: String, _ name: String, _ version: String? = nil) -> BrowserPreferenceItem {
            BrowserPreferenceItem(bundleIdentifier: id, name: name, version: version, icon: nil)
        }

        var installed = [make("com.brave.Browser", "Brave", "1.0")]
        var lookups = 0
        var changes = [[BrowserPreferenceItem]]()
        let refresher = BrowserPreferenceLiveRefresher(
            initialItems: installed,
            discover: {
                lookups += 1
                return installed
            },
            update: { changes.append($0) }
        )
        precondition(!refresher.refreshIfChanged(), "An unchanged inventory must not rebuild rows")
        precondition(changes.isEmpty)
        installed.append(make("com.apple.Safari", "Safari"))
        precondition(refresher.refreshIfChanged(), "New installation should refresh an open window")
        precondition(changes.last?.map(\.bundleIdentifier) == [
            "com.brave.Browser", "com.apple.Safari"
        ])
        precondition(!refresher.refreshIfChanged(), "Do not rebuild rows on every scan")
        installed.removeFirst()
        precondition(refresher.refreshIfChanged(), "Removed browser must vanish while preferences remain open")
        precondition(changes.last?.map(\.bundleIdentifier) == ["com.apple.Safari"])
        installed[0] = make("com.apple.Safari", "Safari", "26.1")
        precondition(refresher.refreshIfChanged(), "Updated metadata must refresh the row")
        precondition(changes.last?.first?.version == "26.1")
        installed.removeAll()
        precondition(refresher.refreshIfChanged(), "Removing the last browser should show empty state")
        precondition(changes.last?.isEmpty == true)
        precondition(lookups == 6 && changes.count == 4, "Each poll runs discovery; only changes update UI")

        // The timer is window-scoped. Trigger it deterministically so CI does
        // not depend on real installed apps or clock scheduling.
        installed = [make("com.google.Chrome", "Chrome")]
        refresher.start(interval: 60)
        guard let timer = refresher.timer, timer.isValid else {
            fatalError("Live refresh must create a repeating timer")
        }
        timer.fire()
        precondition(changes.last?.first?.bundleIdentifier == "com.google.Chrome",
                     "A timer tick must rediscover installed applications")
        refresher.stop()
        precondition(!timer.isValid && refresher.timer == nil,
                     "Closing preferences must stop future scans")
        try testMovedBrowserWhileWindowOpen()
        print("PASS: live installation/removal refresh preserves changes only while preferences are open")
    }

    // Exercise the real inventory + metadata + window-scoped refresh chain.
    // Previous synthetic tests changed arrays without moving application bundles.
    private static func testMovedBrowserWhileWindowOpen() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "pdf-moved-browser-0162-" + UUID().uuidString, isDirectory: true)
        let system = root.appendingPathComponent("Applications", isDirectory: true)
        let user = root.appendingPathComponent("User Applications", isDirectory: true)
        let untracked = root.appendingPathComponent("Unregistered", isDirectory: true)
        for directory in [system, user, untracked] {
            try files.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        defer { try? files.removeItem(at: root) }

        let firstPath = system.appendingPathComponent("Brave Browser.app", isDirectory: true)
        let secondPath = user.appendingPathComponent("Brave Browser.app", isDirectory: true)
        let hiddenPath = untracked.appendingPathComponent("Brave Browser.app", isDirectory: true)
        let executableFolder = firstPath.appendingPathComponent(
            "Contents/MacOS", isDirectory: true)
        try files.createDirectory(at: executableFolder, withIntermediateDirectories: true)
        let info: [String: String] = [
            "CFBundleIdentifier": "com.brave.Browser",
            "CFBundleExecutable": "Browser",
            "CFBundlePackageType": "APPL",
            "CFBundleDisplayName": "Brave Browser",
            "CFBundleShortVersionString": "1.0",
        ]
        let plist = try PropertyListSerialization.data(
            fromPropertyList: info, format: .xml, options: 0)
        try plist.write(to: firstPath.appendingPathComponent("Contents/Info.plist"))
        let launchMarker = root.appendingPathComponent("unexpected-launch")
        let executable = executableFolder.appendingPathComponent("Browser")
        try "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
            .write(to: executable, atomically: true, encoding: .utf8)
        try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: executable.path)

        var scannedPaths = [String]()
        var scans = 0
        func discoverItems() -> [BrowserPreferenceItem] {
            refreshedBrowserPreferenceItems(
                discover: {
                    scans += 1
                    let found = discoverInstalledBrowsers(
                        searchDirectories: [system, user],
                        registeredApplications: [])
                    scannedPaths = found.map(\.path)
                    return found
                },
                metadata: { url in
                    browserApplicationMetadata(at: url, iconLookup: { _ in nil })
                }
            )
        }

        let initial = discoverItems()
        precondition(scannedPaths == [firstPath.path])
        precondition(initial.count == 1
                     && initial[0].bundleIdentifier == "com.brave.Browser")
        precondition(initial[0].name == "Brave Browser"
                     && initial[0].version == "1.0")

        // This view remains alive throughout all three filesystem moves.
        var visible = BrowserPreferenceListView(items: initial)
        var updates = 0
        let refresher = BrowserPreferenceLiveRefresher(
            initialItems: initial,
            discover: { discoverItems() },
            update: { items in
                updates += 1
                visible = BrowserPreferenceListView(items: items)
            })
        refresher.start(interval: 3600)
        guard let timer = refresher.timer, timer.isValid else {
            fatalError("Preferences must keep its periodic discovery active")
        }

        // Move between searched locations without closing the window.
        // Same name, ID, and version need not rebuild a visually identical row,
        // but discovery must use the NEW path, not cached metadata from the old.
        try files.moveItem(at: firstPath, to: secondPath)
        precondition(!files.fileExists(atPath: firstPath.path))
        timer.fire()
        precondition(scannedPaths == [secondPath.path],
                     "A moved application must be discovered at its new physical path")
        precondition(visible.rows.count == 1
                     && visible.rows[0].bundleIdentifier == "com.brave.Browser",
                     "A move between known locations must not drop the browser row")
        precondition(updates == 0,
                     "A move with identical visible metadata need not rebuild the view")

        // Move into a location not searched or registered: the still-open
        // settings window must clear the stale row and show the empty state.
        try files.moveItem(at: secondPath, to: hiddenPath)
        timer.fire()
        precondition(scannedPaths.isEmpty,
                     "Unregistered applications outside discovered paths must be absent")
        precondition(updates == 1 && visible.rows.isEmpty)
        precondition(visible.emptyState?.heading.stringValue == "No browsers found",
                     "A moved-away browser must show the existing recovery guidance")

        // Restore it before closing the same window: the row must return.
        try files.moveItem(at: hiddenPath, to: firstPath)
        timer.fire()
        precondition(scannedPaths == [firstPath.path])
        precondition(updates == 2 && visible.rows.count == 1)
        precondition(visible.emptyState == nil
                     && visible.rows[0].nameField.stringValue == "Brave Browser",
                     "Rediscovery after a move back must restore the browser row")

        refresher.stop()
        precondition(!timer.isValid && refresher.timer == nil)
        precondition(scans == 4, "Each refresh must use fresh discovery")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Discovery and open settings must never execute a browser")
    }
}
