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
        precondition(BrowserPreferenceListView(items: []).rows.isEmpty)

        let blankVersion = encode([[
            "bundleIdentifier": "com.example.Browser",
            "name": " Example Browser ",
            "version": "\n",
        ]])
        let normalized = browserPreferenceItems(from: blankVersion)
        precondition(normalized?.first?.name == "Example Browser")
        precondition(normalized?.first?.version == nil, "Malformed optional version is omitted")

        let invalidNames = ["", "\n", "Browser\nFake", String(repeating: "X", count: 129)]
        for name in invalidNames {
            precondition(browserPreferenceItems(from: encode([[
                "bundleIdentifier": "com.example.Browser", "name": name
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
                "bundleIdentifier": "com.example.Browser",
                "name": "Example Browser",
                "iconTIFFBase64": imageData.base64EncodedString(),
            ]]))
            precondition(iconItems?.first?.icon != nil, "Decode recognizable app artwork")
            precondition(BrowserPreferenceListView(items: iconItems!).rows[0].iconView.image != nil)
        } else {
            fatalError("Could not create test icon fixture")
        }


        // Opening preferences multiple times must query a fresh browser list
        // and fresh metadata; never cache a prior installed-app snapshot.
        let root = FileManager.default.temporaryDirectory
            .appendingPathComponent("pref-refresh-" + UUID().uuidString, isDirectory: true)
        let braveURL = root.appendingPathComponent("Brave.app", isDirectory: true)
        let safariURL = root.appendingPathComponent("Safari.app", isDirectory: true)
        var installed = [InstalledBrowser(bundleIdentifier: "com.brave.Browser",
                                          path: braveURL.path)]
        var version = "1.0"
        var discoveryCount = 0
        var metadataCount = 0
        let discover: () -> [InstalledBrowser] = {
            discoveryCount += 1
            return installed
        }
        let lookup: (URL) -> BrowserApplicationMetadata? = { url in
            metadataCount += 1
            guard url == braveURL || url == safariURL else { return nil }
            let id = url == braveURL ? "com.brave.Browser" : "com.apple.Safari"
            return BrowserApplicationMetadata(
                bundleIdentifier: id, bundleURL: url,
                name: url == braveURL ? "Brave" : "Safari",
                icon: nil, version: version,
                executableURL: url.appendingPathComponent("Contents/MacOS/Browser")
            )
        }
        let first = refreshedBrowserPreferenceItems(discover: discover, metadata: lookup)
        precondition(first.map(\.bundleIdentifier) == ["com.brave.Browser"])
        precondition(first[0].version == "1.0")
        installed.append(InstalledBrowser(bundleIdentifier: "com.apple.Safari",
                                          path: safariURL.path))
        version = "2.0"
        let second = refreshedBrowserPreferenceItems(discover: discover, metadata: lookup)
        precondition(second.map(\.bundleIdentifier) ==
                     ["com.brave.Browser", "com.apple.Safari"],
                     "An installed browser must appear on the next preferences open")
        precondition(second[0].version == "2.0",
                     "Browser version changes must be reflected on reopen")
        installed.removeFirst()
        let third = refreshedBrowserPreferenceItems(discover: discover, metadata: lookup)
        precondition(third.map(\.bundleIdentifier) == ["com.apple.Safari"],
                     "Removed browsers must disappear on the next open")
        precondition(discoveryCount == 3 && metadataCount == 4,
                     "Discovery and metadata must run again on every open")
        precondition(refreshedBrowserPreferenceItems(
            discover: { [InstalledBrowser(bundleIdentifier: "com.fake.Impostor",
                                          path: braveURL.path)] },
            metadata: lookup).isEmpty, "Mismatched bundle identities must not be displayed")
        precondition(refreshedBrowserPreferenceItems(
            discover: { [InstalledBrowser(bundleIdentifier: "com.brave.Browser",
                                          path: braveURL.path)] },
            metadata: { _ in nil }).isEmpty,
            "An application that vanished after discovery must not be displayed")

        print("PASS: browser presentation and fresh discovery on each open; no selection side effects.")
    }
}
