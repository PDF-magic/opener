import AppKit
import Foundation

// Read-only presentation of already-discovered browser metadata. The discovery
// provider and the user's selected PDF target remain separate responsibilities.
// The JSON field names match browser-app-metadata.swift (opener-0129).
struct BrowserPreferenceRecord: Decodable {
    let bundleIdentifier: String
    let name: String
    let version: String?
    let iconTIFFBase64: String?
}

struct BrowserPreferenceItem {
    let bundleIdentifier: String
    let name: String
    let version: String?
    let icon: NSImage?
}

private let supportedBrowserBundleIDs: Set<String> = [
    "com.brave.Browser",
    "com.google.Chrome",
    "org.chromium.Chromium",
    "com.microsoft.edgemac",
    "com.vivaldi.Vivaldi",
    "com.operasoftware.Opera",
    "company.thebrowser.Browser",
    "org.mozilla.firefox",
    "com.apple.Safari",
]

private func safeBrowserDisplayText(_ raw: String, limit: Int) -> String? {
    let value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !value.isEmpty, value.count <= limit,
          !value.unicodeScalars.contains(where: {
              CharacterSet.controlCharacters.contains($0)
          }) else { return nil }
    return value
}

// Never read bundle paths or execute an application while displaying entries.
// A malformed list is rejected as a whole rather than showing misleading names.
func browserPreferenceItems(from data: Data) -> [BrowserPreferenceItem]? {
    guard data.count <= 4 * 1024 * 1024,
          let records = try? JSONDecoder().decode([BrowserPreferenceRecord].self, from: data),
          records.count <= 100 else { return nil }

    var items = [BrowserPreferenceItem]()
    for record in records {
        guard record.bundleIdentifier.count <= 255,
              record.bundleIdentifier.range(
                  of: "^[A-Za-z0-9][A-Za-z0-9.-]{1,254}$",
                  options: .regularExpression
              ) != nil,
              record.bundleIdentifier.contains("."),
          !record.bundleIdentifier.contains(".."),
          record.bundleIdentifier != "local.studio.brave-pdf-opener",
              let name = safeBrowserDisplayText(record.name, limit: 128) else { return nil }

        // An installed application's name or similar ID does not mean it is
        // supported in the primary list. Manual custom targets remain separate.
        guard supportedBrowserBundleIDs.contains(record.bundleIdentifier) else { continue }

        // The version is an optional detail, never a reason to invent one.
        let version = record.version.flatMap {
            safeBrowserDisplayText($0, limit: 64)
        }
        var icon: NSImage?
        if let encoded = record.iconTIFFBase64,
           encoded.utf8.count <= 3 * 1024 * 1024,
           let bytes = Data(base64Encoded: encoded),
           bytes.count <= 2 * 1024 * 1024 {
            icon = NSImage(data: bytes)
        }
        items.append(BrowserPreferenceItem(
            bundleIdentifier: record.bundleIdentifier, name: name,
            version: version, icon: icon
        ))
    }
    return items
}

// Load a fresh inventory on each preferences open, not the previous window's
// snapshot. Installed apps can appear, disappear, or change while the app runs.
func refreshedBrowserPreferenceItems(
    discover: () -> [InstalledBrowser],
    metadata: (URL) -> BrowserApplicationMetadata?
) -> [BrowserPreferenceItem] {
    var items = [BrowserPreferenceItem]()
    for browser in discover() {
        if items.count >= 100 { break }
        let url = URL(fileURLWithPath: browser.path, isDirectory: true)
        guard url.pathExtension.lowercased() == "app",
              let details = metadata(url),
              details.bundleIdentifier == browser.bundleIdentifier,
              details.bundleURL.standardizedFileURL.resolvingSymlinksInPath()
                  == url.standardizedFileURL.resolvingSymlinksInPath(),
              let name = safeBrowserDisplayText(details.name, limit: 128),
              browser.bundleIdentifier != "local.studio.brave-pdf-opener",
              supportedBrowserBundleIDs.contains(browser.bundleIdentifier),
              browser.bundleIdentifier.count <= 255,
              browser.bundleIdentifier.range(
                  of: "^[A-Za-z0-9][A-Za-z0-9.-]{1,254}$",
                  options: .regularExpression
              ) != nil,
              browser.bundleIdentifier.contains("."),
              !browser.bundleIdentifier.contains("..") else { continue }
        items.append(BrowserPreferenceItem(
            bundleIdentifier: browser.bundleIdentifier, name: name,
            version: details.version.flatMap {
                safeBrowserDisplayText($0, limit: 64)
            }, icon: details.icon
        ))
    }
    return items
}

func refreshedBrowserPreferenceItems() -> [BrowserPreferenceItem] {
    refreshedBrowserPreferenceItems(
        discover: {
            discoverInstalledBrowsers(
                searchDirectories: browserSearchDirectories(),
                registeredApplications: registeredBrowserApplications()
            )
        },
        metadata: { browserApplicationMetadata(at: $0) }
    )
}

// The browser's actual macOS icon and human-readable name are always in the
// main row. Version appears only when the user requests optional details.
final class BrowserPreferenceRow: NSStackView {
    let bundleIdentifier: String
    let nameField: NSTextField
    let iconView: NSImageView
    let versionField: NSTextField?
    let detailsButton: NSButton?

    init(item: BrowserPreferenceItem) {
        bundleIdentifier = item.bundleIdentifier
        nameField = NSTextField(labelWithString: item.name)
        iconView = NSImageView()
        if let version = item.version {
            versionField = NSTextField(labelWithString: "Version \(version)")
            detailsButton = NSButton(title: "Show version", target: nil, action: nil)
        } else {
            versionField = nil
            detailsButton = nil
        }

        super.init(frame: .zero)
        orientation = .vertical
        alignment = .leading
        spacing = 5

        let mainRow = NSStackView()
        mainRow.orientation = .horizontal
        mainRow.alignment = .centerY
        mainRow.spacing = 10

        iconView.image = item.icon ?? NSImage(named: NSImage.Name("NSApplicationIcon"))
        iconView.imageScaling = .scaleProportionallyUpOrDown
        iconView.translatesAutoresizingMaskIntoConstraints = false
        NSLayoutConstraint.activate([
            iconView.widthAnchor.constraint(equalToConstant: 32),
            iconView.heightAnchor.constraint(equalToConstant: 32),
        ])
        iconView.setAccessibilityLabel("\(item.name) application icon")
        mainRow.addArrangedSubview(iconView)

        nameField.font = .systemFont(ofSize: 14, weight: .medium)
        nameField.lineBreakMode = .byTruncatingTail
        mainRow.addArrangedSubview(nameField)

        if let button = detailsButton {
            button.bezelStyle = .rounded
            button.target = self
            button.action = #selector(toggleDetails(_:))
            button.setAccessibilityLabel("Show version for \(item.name)")
            mainRow.addArrangedSubview(button)
        }
        addArrangedSubview(mainRow)

        if let version = versionField {
            version.textColor = .secondaryLabelColor
            version.font = .systemFont(ofSize: 12)
            version.isHidden = true
            addArrangedSubview(version)
        }
    }

    required init?(coder: NSCoder) { return nil }

    @objc func toggleDetails(_ sender: NSButton) {
        guard let version = versionField else { return }
        version.isHidden.toggle()
        sender.title = version.isHidden ? "Show version" : "Hide version"
        sender.setAccessibilityLabel(
            "\(version.isHidden ? "Show" : "Hide") version for \(nameField.stringValue)"
        )
    }
}

// The discovery consumer may receive a valid empty list. Explain how to
// recover without treating the empty result as a reason to reset preferences.
final class BrowserPreferenceEmptyStateView: NSStackView {
    let heading = NSTextField(labelWithString: "No browsers found")
    let guidance = NSTextField(wrappingLabelWithString:
        "Install a browser or check that discovery includes its installation location, then run browser discovery again.")
    let preferenceNote = NSTextField(wrappingLabelWithString:
        "Your existing PDF application preference has not changed.")

    override init(frame: NSRect) {
        super.init(frame: frame)
        orientation = .vertical
        alignment = .leading
        spacing = 8

        heading.font = .systemFont(ofSize: 15, weight: .semibold)
        guidance.textColor = .secondaryLabelColor
        preferenceNote.textColor = .secondaryLabelColor
        guidance.preferredMaxLayoutWidth = 440
        preferenceNote.preferredMaxLayoutWidth = 440

        addArrangedSubview(heading)
        addArrangedSubview(guidance)
        addArrangedSubview(preferenceNote)
    }

    required init?(coder: NSCoder) { return nil }
}

final class BrowserPreferenceListView: NSStackView {
    private(set) var rows = [BrowserPreferenceRow]()
    let refreshButton: NSButton?
    let refreshStatus: NSTextField?
    var onItemsChanged: ((Int) -> Void)?
    private let refreshProvider: ((@escaping ([BrowserPreferenceItem]?) -> Void) -> Void)?
    private(set) var emptyState: BrowserPreferenceEmptyStateView?

    init(
        items: [BrowserPreferenceItem],
        refreshProvider: ((@escaping ([BrowserPreferenceItem]?) -> Void) -> Void)? = nil
    ) {
        self.refreshProvider = refreshProvider
        if refreshProvider != nil {
            refreshButton = NSButton(title: "Refresh Browsers", target: nil, action: nil)
            refreshStatus = NSTextField(labelWithString: "")
        } else {
            refreshButton = nil
            refreshStatus = nil
        }
        super.init(frame: .zero)
        orientation = .vertical
        alignment = .leading
        spacing = 12

        if let button = refreshButton {
            button.target = self
            button.action = #selector(refreshBrowsers(_:))
            button.setAccessibilityLabel("Refresh Browsers")
            addArrangedSubview(button)
        }
        if let status = refreshStatus {
            status.textColor = .secondaryLabelColor
            status.setAccessibilityLabel("Browser refresh status")
            addArrangedSubview(status)
        }
        replaceItems(items)
    }

    required init?(coder: NSCoder) { return nil }

    private func replaceItems(_ items: [BrowserPreferenceItem]) {
        // Preserve the user's open version details for surviving browsers.
        let expanded = Set(rows.filter { $0.versionField?.isHidden == false }
            .map { $0.bundleIdentifier })
        for row in rows {
            removeArrangedSubview(row)
            row.removeFromSuperview()
        }
        if let oldEmptyState = emptyState {
            removeArrangedSubview(oldEmptyState)
            oldEmptyState.removeFromSuperview()
            emptyState = nil
        }
        rows = items.map { BrowserPreferenceRow(item: $0) }
        if rows.isEmpty {
            let view = BrowserPreferenceEmptyStateView(frame: .zero)
            emptyState = view
            addArrangedSubview(view)
        } else {
            for row in rows {
                if expanded.contains(row.bundleIdentifier), let button = row.detailsButton {
                    row.toggleDetails(button)
                }
                addArrangedSubview(row)
            }
        }
        onItemsChanged?(rows.count)
    }

    @objc func refreshBrowsers(_ sender: NSButton) {
        guard let provider = refreshProvider, sender.isEnabled else { return }
        sender.isEnabled = false
        refreshStatus?.stringValue = "Refreshing browsers…"
        provider { [weak self] updated in
            DispatchQueue.main.async {
                guard let self = self else { return }
                if let updated = updated {
                    self.replaceItems(updated)
                    self.refreshStatus?.stringValue = "Browser list refreshed."
                } else {
                    // Failed/invalid discovery is not an empty inventory.
                    self.refreshStatus?.stringValue = "Refresh failed. Existing list kept."
                }
                self.refreshButton?.isEnabled = true
            }
        }
    }
}

#if !BROWSER_PREFERENCE_TESTING
private final class BrowserPreferenceWindowDelegate: NSObject, NSWindowDelegate {
    func windowWillClose(_ notification: Notification) {
        NSApp.terminate(nil)
    }
}

@main
struct ShowBrowserPreferences {
    static func main() {
        // The normal window-open path always refreshes discovery. Explicit
        // stdin mode retains compatibility with callers supplying metadata.
        let arguments = Array(CommandLine.arguments.dropFirst())
        guard arguments.isEmpty || arguments == ["--metadata-stdin"] else {
            fputs("Usage: browser-preference-list [--metadata-stdin]\n", stderr)
            exit(EXIT_FAILURE)
        }
        let items: [BrowserPreferenceItem]
        if arguments == ["--metadata-stdin"] {
            let input = FileHandle.standardInput.readData(ofLength: 4 * 1024 * 1024 + 1)
            guard let supplied = browserPreferenceItems(from: input) else {
                fputs("Expected a JSON array of discovered browser metadata.\n", stderr)
                exit(EXIT_FAILURE)
            }
            items = supplied
        } else {
            items = refreshedBrowserPreferenceItems()
        }

        let app = NSApplication.shared
        app.setActivationPolicy(.regular)
        let window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 540, height: 420),
            styleMask: [.titled, .closable, .resizable],
            backing: .buffered, defer: false
        )
        window.title = "Installed browser preferences"
        window.minSize = NSSize(width: 420, height: 220)

        let list = BrowserPreferenceListView(items: items, refreshProvider: { completion in
            DispatchQueue.global(qos: .userInitiated).async {
                completion(refreshedBrowserPreferenceItems())
            }
        })
        let contentHeight = max(120, CGFloat(max(items.count, 1)) * 84 + 100)
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 520, height: contentHeight))
        list.frame = NSRect(x: 16, y: 16, width: 488, height: contentHeight - 32)
        document.addSubview(list)
        list.onItemsChanged = { [weak document, weak list] count in
            let height = max(120, CGFloat(max(count, 1)) * 84 + 100)
            document?.setFrameSize(NSSize(width: 520, height: height))
            if let list = list {
                list.frame = NSRect(x: 16, y: 16, width: 488, height: height - 32)
            }
        }

        let scrolling = NSScrollView(frame: window.contentView?.bounds ?? .zero)
        scrolling.autoresizingMask = [.width, .height]
        scrolling.hasVerticalScroller = true
        scrolling.documentView = document
        window.contentView = scrolling

        let closeHandler = BrowserPreferenceWindowDelegate()
        window.delegate = closeHandler
        window.center()
        window.makeKeyAndOrderFront(nil)
        app.activate(ignoringOtherApps: true)
        app.run()
        withExtendedLifetime(closeHandler) {}
    }
}
#endif
