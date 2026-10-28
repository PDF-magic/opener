import AppKit
import Foundation

// Test an explicitly selected browser disappearing after preference selection.
// Only disposable app bundles and a temporary preference file are modified.
@main
struct RemovedSelectedBrowserDiscoveryTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "selected-browser-removed-0159-" + UUID().uuidString, isDirectory: true)
        let applications = root.appendingPathComponent("Applications", isDirectory: true)
        try files.createDirectory(at: applications, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-launch")
        func makeApp(_ name: String, bundleID: String) throws -> URL {
            let app = applications.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let info: [String: String] = [
                "CFBundleIdentifier": bundleID,
                "CFBundleExecutable": "TestBrowser",
                "CFBundlePackageType": "APPL",
                "CFBundleName": name,
            ]
            let encoded = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try encoded.write(to: app.appendingPathComponent("Contents/Info.plist"))
            let executable = macos.appendingPathComponent("TestBrowser")
            try "#!/bin/sh\nprintf opened > \"\(launchMarker.path)\"\n".write(
                to: executable, atomically: true, encoding: .utf8)
            try files.setAttributes(
                [.posixPermissions: 0o755], ofItemAtPath: executable.path)
            return app
        }

        let selectedID = "com.brave.Browser"
        let selected = try makeApp("Brave Browser", bundleID: selectedID)
        let remaining = try makeApp("Safari", bundleID: "com.apple.Safari")
        let preference = root.appendingPathComponent("target-app.txt")
        try (selectedID + "\n").write(to: preference, atomically: true, encoding: .utf8)

        func discovered() -> [InstalledBrowser] {
            discoverInstalledBrowsers(
                searchDirectories: [applications], additionalApplications: [],
                registeredApplications: [])
        }
        func items() -> [BrowserPreferenceItem] {
            refreshedBrowserPreferenceItems(
                discover: discovered,
                metadata: { browserApplicationMetadata(at: $0, iconLookup: { _ in nil }) }
            )
        }

        let before = discovered()
        precondition(Set(before.map(\.bundleIdentifier)) ==
                     Set([selectedID, "com.apple.Safari"]))
        let firstItems = items()
        precondition(firstItems.contains { $0.bundleIdentifier == selectedID })
        precondition(resolveVerifiedPDFApplication(
            bundleIdentifier: selectedID, lookupAll: { _ in [selected] }) == selected,
            "A present selected app should pass native bundle resolution")

        var changes = [[BrowserPreferenceItem]]()
        let refresher = BrowserPreferenceLiveRefresher(
            initialItems: firstItems, discover: items,
            update: { changes.append($0) }
        )
        try files.removeItem(at: selected)

        precondition(discovered() == [
            InstalledBrowser(bundleIdentifier: "com.apple.Safari", path: remaining.path)
        ], "Removal must not leave stale selected-browser discovery records")
        precondition(refresher.refreshIfChanged(),
                     "Preferences must refresh when the selected browser disappears")
        precondition(changes.last?.map(\.bundleIdentifier) == ["com.apple.Safari"])
        precondition(!refresher.refreshIfChanged(),
                     "Unchanged discovery must not trigger another update")
        precondition(resolveVerifiedPDFApplication(
            bundleIdentifier: selectedID, lookupAll: { _ in [selected, remaining] }) == nil,
            "The missing selected bundle must not silently fall back to Safari")
        precondition(usableDiscoveredApplications([selected, remaining]) == [remaining],
                     "Stale Launch Services paths must be excluded")
        precondition(!targetSupportsPDF(
            application: resolveVerifiedPDFApplication(
                bundleIdentifier: selectedID, lookupAll: { _ in [selected] }),
            registeredPDFHandlers: [remaining]),
            "A remaining PDF handler cannot authorize the removed selected browser")
        let persistedAfterRemoval = try String(contentsOf: preference, encoding: .utf8)
        precondition(persistedAfterRemoval == selectedID + "\n",
                     "Removal must not rewrite the user's saved browser selection")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "Discovery and preference refresh must not launch an application")

        // Removing the last browser should display recovery guidance, but
        // still never erase or replace the saved selected browser.
        try files.removeItem(at: remaining)
        precondition(refresher.refreshIfChanged())
        precondition(changes.last?.isEmpty == true)
        precondition(BrowserPreferenceListView(items: changes.last!).emptyState != nil)
        let persistedAfterEmpty = try String(contentsOf: preference, encoding: .utf8)
        precondition(persistedAfterEmpty == selectedID + "\n")
        precondition(!files.fileExists(atPath: launchMarker.path))
        print("PASS: selected browser removal, refresh, preserved preference, safe PDF preflight")
    }
}
