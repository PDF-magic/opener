import AppKit
import Foundation

@main
struct BrowserPreferenceListTests {
    static func main() {
        func encode(_ records: [[String: Any]]) -> Data {
            return try! JSONSerialization.data(withJSONObject: records)
        }
        let entries: [[String: Any]] = [
            [
                "bundleIdentifier": "com.brave.Browser",
                "name": "Brave Browser",
                "version": "1.74.25",
                "iconTIFFBase64": NSNull(),
                "bundlePath": "/Applications/Brave Browser.app",
                "executablePath": "/Applications/Brave Browser.app/Contents/MacOS/Brave",
            ],
            [
                "bundleIdentifier": "com.apple.Safari",
                "name": "Safari",
                "version": NSNull(),
                "iconTIFFBase64": NSNull(),
            ],
        ]
        let valid = browserPreferenceItems(from: encode(entries))
        precondition(valid?.count == 2, "Show every supplied browser without changing discovery order")
        precondition(valid?[0].name == "Brave Browser", "Show the recognizable browser name")
        precondition(valid?[0].version == "1.74.25", "Retain optional version metadata")
        precondition(valid?[1].version == nil, "Missing version remains absent")

        let list = BrowserPreferenceListView(items: valid!)
        precondition(list.rows.count == 2, "One visible row per discovered browser")
        let brave = list.rows[0]
        precondition(brave.nameField.stringValue == "Brave Browser")
        precondition(brave.iconView.frame.width >= 0, "Each row includes an icon view")
        precondition(brave.versionField?.isHidden == true, "Version hidden by default")
        precondition(brave.detailsButton?.title == "Show version")
        brave.toggleDetails(brave.detailsButton!)
        precondition(brave.versionField?.isHidden == false, "Details reveal version")
        precondition(brave.versionField?.stringValue == "Version 1.74.25")
        brave.toggleDetails(brave.detailsButton!)
        precondition(brave.versionField?.isHidden == true, "Details can be closed")
        precondition(list.rows[1].detailsButton == nil,
                     "Do not present a fake version or disclosure when unavailable")
        precondition(list.rows[1].nameField.stringValue == "Safari")
        // A valid empty discovery result gets actionable guidance, not a
        // blank list or a synthetic browser choice.
        precondition(list.emptyState == nil, "Nonempty results never show an empty state")
        precondition(browserPreferenceItems(from: encode([]))?.isEmpty == true,
                     "Valid empty discovery results remain distinct from malformed data")
        let emptyList = BrowserPreferenceListView(items: [])
        precondition(emptyList.rows.isEmpty, "Empty results cannot create a fake browser row")
        guard let emptyState = emptyList.emptyState else {
            fatalError("An empty list must render recovery guidance")
        }
        precondition(emptyList.arrangedSubviews.count == 1,
                     "The empty state replaces browser rows")
        precondition(emptyState.heading.stringValue == "No browsers found")
        precondition(emptyState.guidance.stringValue.contains("Install a browser"),
                     "Suggest an actionable installation check")
        precondition(emptyState.guidance.stringValue.contains("discovery again"),
                     "Explain how to retry browser discovery")
        precondition(emptyState.preferenceNote.stringValue.contains("has not changed"),
                     "Do not imply the saved PDF target was reset")

        let unsupported = encode([
            [
                "bundleIdentifier": "com.example.FakeBrowser",
                "name": "Unsupported Browser",
            ],
            [
                "bundleIdentifier": "com.brave.Browser.beta",
                "name": "Brave Beta",
            ],
            [
                "bundleIdentifier": "com.google.Chrome",
                "name": "Google Chrome",
            ],
            [
                "bundleIdentifier": "com.google.Chrome.fake",
                "name": "Google Chrome",
            ],
        ])
        let primaryItems = browserPreferenceItems(from: unsupported)
        precondition(primaryItems?.count == 1,
                     "Hide unsupported and preview browsers from primary list")
        precondition(primaryItems?.first?.bundleIdentifier == "com.google.Chrome")
        precondition(browserPreferenceItems(from: encode([[
            "bundleIdentifier": "com.example.Custom",
            "name": "Custom Browser",
        ]]))?.isEmpty == true,
                     "Unsupported browser alone produces an empty primary list")
        precondition(BrowserPreferenceListView(items: primaryItems!).rows.count == 1)

        let blankVersion = encode([[
            "bundleIdentifier": "com.brave.Browser",
            "name": " Example Browser ",
            "version": "\n",
        ]])
        let normalized = browserPreferenceItems(from: blankVersion)
        precondition(normalized?.first?.name == "Example Browser")
        precondition(normalized?.first?.version == nil, "Malformed optional version is omitted")

        let invalidNames = ["", "\n", "Browser\nFake", String(repeating: "X", count: 129)]
        for name in invalidNames {
            precondition(browserPreferenceItems(from: encode([[
                "bundleIdentifier": "com.brave.Browser", "name": name
            ]])) == nil, "Reject misleading labels")
        }
        for identifier in ["", "bad-id", "com..broken", "local.studio.brave-pdf-opener"] {
            precondition(browserPreferenceItems(from: encode([[
                "bundleIdentifier": identifier, "name": "Browser"
            ]])) == nil, "Reject invalid or self-referential IDs")
        }
        precondition(browserPreferenceItems(from: Data("not json".utf8)) == nil)
        precondition(browserPreferenceItems(from: encode(Array(repeating: entries[0], count: 101))) == nil,
                     "Bound the number of rows")
        precondition(browserPreferenceItems(from: Data(repeating: 0, count: 4 * 1024 * 1024 + 1)) == nil,
                     "Bound input size")

        // A valid icon payload must use the actual supplied artwork, rather
        // than substituting a static logo based on the browser's name.
        let image = NSImage(size: NSSize(width: 16, height: 16))
        image.lockFocus()
        NSColor.systemBlue.setFill()
        NSBezierPath(rect: NSRect(x: 0, y: 0, width: 16, height: 16)).fill()
        image.unlockFocus()
        if let imageData = image.tiffRepresentation {
            let iconItems = browserPreferenceItems(from: encode([[
                "bundleIdentifier": "com.brave.Browser",
                "name": "Example Browser",
                "iconTIFFBase64": imageData.base64EncodedString(),
            ]]))
            precondition(iconItems?.first?.icon != nil, "Decode recognizable app artwork")
            precondition(BrowserPreferenceListView(items: iconItems!).rows[0].iconView.image != nil)
        } else {
            fatalError("Could not create test icon fixture")
        }

        // The refresh button invokes the provider on demand, updates rows,
        // preserves expanded details, and never treats a provider failure as
        // successful discovery of an empty list.
        var pendingRefresh: (([BrowserPreferenceItem]?) -> Void)?
        var refreshCalls = 0
        let refreshing = BrowserPreferenceListView(items: valid!) { completion in
            refreshCalls += 1
            pendingRefresh = completion
        }
        precondition(refreshing.refreshButton?.title == "Refresh Browsers")
        precondition(refreshCalls == 0, "Discovery must not run until requested")
        let refreshButton = refreshing.refreshButton!
        refreshing.rows[0].toggleDetails(refreshing.rows[0].detailsButton!)
        refreshing.refreshBrowsers(refreshButton)
        precondition(refreshCalls == 1 && !refreshButton.isEnabled)
        refreshing.refreshBrowsers(refreshButton)
        precondition(refreshCalls == 1, "Do not start concurrent refreshes")
        pendingRefresh?([valid![0]])
        RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        precondition(refreshButton.isEnabled && refreshing.rows.count == 1)
        precondition(refreshing.rows[0].versionField?.isHidden == false,
                     "Keep existing version disclosure open after refresh")
        precondition(refreshing.refreshStatus?.stringValue == "Browser list refreshed.")

        refreshing.refreshBrowsers(refreshButton)
        pendingRefresh?(nil)
        RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        precondition(refreshing.rows.count == 1, "Failed discovery must retain rows")
        precondition(refreshing.refreshStatus?.stringValue.contains("Existing list kept") == true)

        refreshing.refreshBrowsers(refreshButton)
        pendingRefresh?([])
        RunLoop.current.run(until: Date().addingTimeInterval(0.15))
        precondition(refreshing.rows.isEmpty, "A valid empty inventory may clear rows")
        precondition(refreshButton.isEnabled)
        precondition(BrowserPreferenceListView(items: valid!).refreshButton == nil,
                     "Existing callers without a refresh provider remain unchanged")

        // Build an isolated fake .app and an explicit discovery helper to
        // exercise the real refresh pipeline without querying installed user
        // browsers, changing settings, or launching a browser.
        let manager = FileManager.default
        let root = manager.temporaryDirectory.appendingPathComponent(
            "opener-refresh-test-" + UUID().uuidString)
        try! manager.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? manager.removeItem(at: root) }
        let app = root.appendingPathComponent("Refresh Browser.app")
        let macos = app.appendingPathComponent("Contents/MacOS")
        try! manager.createDirectory(at: macos, withIntermediateDirectories: true)
        let info: [String: String] = [
            "CFBundleIdentifier": "com.brave.Browser",
            "CFBundleExecutable": "Browser",
            "CFBundleDisplayName": "Refreshed Browser",
            "CFBundleShortVersionString": "2.1",
            "CFBundlePackageType": "APPL",
        ]
        let plist = try! PropertyListSerialization.data(
            fromPropertyList: info, format: .xml, options: 0)
        try! plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
        let browserExecutable = macos.appendingPathComponent("Browser")
        try! "#!/bin/sh\nexit 0\n".write(
            to: browserExecutable, atomically: true, encoding: .utf8)
        try! manager.setAttributes(
            [.posixPermissions: 0o755], ofItemAtPath: browserExecutable.path)
        let discoveredData = encode([[
            "bundleIdentifier": "com.brave.Browser",
            "path": app.path,
        ]])
        let decoded = refreshedBrowserPreferenceItems(from: discoveredData)
        precondition(decoded?.count == 1 && decoded?.first?.name == "Refreshed Browser")
        precondition(decoded?.first?.version == "2.1")
        precondition(refreshedBrowserPreferenceItems(from: encode([[
            "bundleIdentifier": "com.google.Chrome",
            "path": app.path,
        ]]))?.isEmpty == true, "Mismatched bundle identities never become rows")
        precondition(refreshedBrowserPreferenceItems(from: Data("bad".utf8)) == nil)
        precondition(refreshedBrowserPreferenceItems(
            from: Data(repeating: 0, count: 256 * 1024 + 1)) == nil)

        let inventory = root.appendingPathComponent("inventory.json")
        try! discoveredData.write(to: inventory)
        let helper = root.appendingPathComponent("discover-browser-fixture.sh")
        try! ("#!/bin/sh\n/bin/cat \"" + inventory.path + "\"\n").write(
            to: helper, atomically: true, encoding: .utf8)
        try! manager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: helper.path)
        precondition(rediscoverBrowserPreferenceItems(executable: helper)?.first?.name
                     == "Refreshed Browser", "Refresh executes read-only discovery again")
        try! "#!/bin/sh\nexit 3\n".write(
            to: helper, atomically: true, encoding: .utf8)
        precondition(rediscoverBrowserPreferenceItems(executable: helper) == nil,
                     "A failed discovery process leaves previous rows untouched")
        precondition(rediscoverBrowserPreferenceItems(
            executable: root.appendingPathComponent("missing-helper")) == nil)

        print("PASS: browser icons, names and optional version disclosure; no selection side effects.")
    }
}
