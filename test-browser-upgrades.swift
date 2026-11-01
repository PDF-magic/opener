import AppKit
import Foundation

// Browser upgrades are simulated with disposable application bundles. Neither
// preferences nor the scanner, Launch Services registration, or real browsers
// are modified or launched.
@main
struct BrowserUpgradeTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "opener-browser-upgrade-1066-" + UUID().uuidString, isDirectory: true)
        let applications = root.appendingPathComponent("Applications", isDirectory: true)
        try files.createDirectory(at: applications, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: root) }

        let selectedID = "com.brave.Browser"
        let browser = applications.appendingPathComponent("Brave Browser.app", isDirectory: true)
        let safari = applications.appendingPathComponent("Safari.app", isDirectory: true)
        let marker = root.appendingPathComponent("unexpected-browser-execution")
        let preference = root.appendingPathComponent("target-app.txt")
        try (selectedID + "\n").write(to: preference, atomically: true, encoding: .utf8)
        let originalPreference = try Data(contentsOf: preference)

        func makeApp(at app: URL, identifier: String, version: String,
                     executable: Bool = true) throws {
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let info = [
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "Browser",
                "CFBundlePackageType": "APPL",
                "CFBundleDisplayName": app.lastPathComponent == "Safari.app"
                    ? "Safari" : "Brave Browser",
                "CFBundleShortVersionString": version,
            ]
            let data = try PropertyListSerialization.data(
                fromPropertyList: info, format: .xml, options: 0)
            try data.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let binary = macos.appendingPathComponent("Browser")
                try "#!/bin/sh\nprintf launched > \"\(marker.path)\"\n"
                    .write(to: binary, atomically: true, encoding: .utf8)
                try files.setAttributes([.posixPermissions: 0o755],
                                        ofItemAtPath: binary.path)
            }
        }

        func items() -> [BrowserPreferenceItem] {
            refreshedBrowserPreferenceItems(
                discover: {
                    discoverInstalledBrowsers(
                        searchDirectories: [applications],
                        additionalApplications: [], registeredApplications: [])
                },
                metadata: {
                    browserApplicationMetadata(at: $0, iconLookup: { _ in nil })
                }
            )
        }

        func selectedVersion(_ entries: [BrowserPreferenceItem]) -> String? {
            entries.first { $0.bundleIdentifier == selectedID }?.version
        }

        func resolvedSelected() -> URL? {
            resolveVerifiedPDFApplication(
                bundleIdentifier: selectedID,
                lookupAll: { _ in [browser, safari] }
            )
        }

        // A PDF-capable registered handler is not enough to bypass verification:
        // the *selected* on-disk bundle must also exist and be executable.
        func selectedPDFPreflight() -> Bool {
            targetSupportsPDF(
                application: resolvedSelected(), registeredPDFHandlers: [browser, safari])
        }

        try makeApp(at: browser, identifier: selectedID, version: "1.0")
        try makeApp(at: safari, identifier: "com.apple.Safari", version: "26.0")
        let initial = items()
        precondition(initial.count == 2 && selectedVersion(initial) == "1.0")
        precondition(resolvedSelected() == browser && selectedPDFPreflight())

        var visible = BrowserPreferenceListView(items: initial)
        var updateCount = 0
        let refresher = BrowserPreferenceLiveRefresher(
            initialItems: initial, discover: items,
            update: {
                updateCount += 1
                visible = BrowserPreferenceListView(items: $0)
            })

        func replaceBrowser(with identifier: String, version: String,
                            executable: Bool = true, revision: Int) throws {
            let staged = root.appendingPathComponent("staged-\(revision).app", isDirectory: true)
            let previous = root.appendingPathComponent("previous-\(revision).app", isDirectory: true)
            try makeApp(at: staged, identifier: identifier, version: version,
                        executable: executable)
            try files.moveItem(at: browser, to: previous)
            try files.moveItem(at: staged, to: browser)
        }

        // The browser vendor replaces an installed stable bundle at the *same*
        // location. Refresh must reread its version, without changing the ID,
        // creating duplicate rows or silently switching to another browser.
        try replaceBrowser(with: selectedID, version: "2.0", revision: 1)
        precondition(refresher.refreshIfChanged(),
                     "An in-place browser upgrade must refresh the visible version")
        precondition(selectedVersion(items()) == "2.0")
        precondition(visible.rows.count == 2)
        precondition(visible.rows.filter { $0.bundleIdentifier == selectedID }.count == 1)
        precondition(resolvedSelected() == browser && selectedPDFPreflight())
        precondition(!refresher.refreshIfChanged(),
                     "An unchanged upgraded browser must not repeatedly rebuild rows")

        // An interrupted upgrade may install a bundle with no executable.
        // Discovery must drop it and native PDF-target preflight must fail
        // closed rather than falling back to the still-present Safari.
        try replaceBrowser(with: selectedID, version: "2.1",
                           executable: false, revision: 2)
        precondition(refresher.refreshIfChanged())
        precondition(selectedVersion(items()) == nil)
        precondition(resolvedSelected() == nil && !selectedPDFPreflight(),
                     "A broken upgrade must never authorize a PDF launch")
        precondition(visible.rows.count == 1
                     && visible.rows[0].bundleIdentifier == "com.apple.Safari")

        // A replacement with a different bundle identifier is equally
        // untrusted, even if its pathname and display name are unchanged.
        try replaceBrowser(with: "com.example.Impostor", version: "2.2", revision: 3)
        precondition(!refresher.refreshIfChanged())
        precondition(resolvedSelected() == nil && !selectedPDFPreflight())

        // A repaired update restores the exact selected browser. No preference
        // migration, default reset, or scanner-policy change is needed.
        try replaceBrowser(with: selectedID, version: "3.0", revision: 4)
        precondition(refresher.refreshIfChanged())
        precondition(selectedVersion(items()) == "3.0")
        precondition(resolvedSelected() == browser && selectedPDFPreflight())
        precondition(updateCount == 3)
        let preservedPreference = try Data(contentsOf: preference)
        precondition(preservedPreference == originalPreference,
                     "Upgrading a browser must preserve the user's target-app.txt")
        precondition(!files.fileExists(atPath: marker.path),
                     "Read-only discovery, refresh and preflight must not execute browsers")
        print("PASS: in-place browser upgrades, broken replacements, safe recovery, and saved selection")
    }
}
