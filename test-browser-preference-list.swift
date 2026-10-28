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

        // The extra-applications control is a disclosure, not a selection or
        // change to the user's PDF target. Legacy array input still works.
        let legacy = browserPreferenceDisplay(from: encode(entries))
        precondition(legacy?.browsers.count == 2 && legacy?.applications.isEmpty == true)
        let envelope: [String: Any] = [
            "browsers": entries,
            "applications": [
                ["name": "PDF Reader", "bundleIdentifier": "org.example.Reader",
                 "path": "/Applications/PDF Reader.app"],
                ["name": "Brave duplicate", "bundleIdentifier": "com.brave.Browser",
                 "path": "/Applications/Brave.app"],
                ["name": "Invalid\nApp", "bundleIdentifier": "org.example.invalid",
                 "path": "/Applications/Invalid.app"],
                ["name": "Unverified", "bundleIdentifier": "org.example.unverified"],
            ],
        ]
        let payload = try! JSONSerialization.data(withJSONObject: envelope)
        let display = browserPreferenceDisplay(from: payload)
        precondition(display?.browsers.count == 2)
        precondition(display?.applications.count == 1)
        precondition(display?.applications.first?.name == "PDF Reader")
        let additionalList = BrowserPreferenceListView(
            items: display!.browsers, additionalApplications: display!.applications)
        precondition(additionalList.additionalSection.isHidden)
        precondition(additionalList.additionalButton.title == "Show additional installed applications")
        additionalList.toggleAdditionalApplications(additionalList.additionalButton)
        precondition(!additionalList.additionalSection.isHidden)
        precondition(additionalList.additionalButton.title == "Hide additional installed applications")
        let shown = additionalList.additionalSection.arrangedSubviews
            .compactMap { ($0 as? NSTextField)?.stringValue }
        precondition(shown == ["PDF Reader [org.example.Reader]"],
                     "Only validated additional application labels should appear")
        additionalList.toggleAdditionalApplications(additionalList.additionalButton)
        precondition(additionalList.additionalSection.isHidden)
        precondition(browserPreferenceDisplay(from: Data("not json".utf8)) == nil)

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

        print("PASS: browser icons, names and optional version disclosure; no selection side effects.")
    }
}
