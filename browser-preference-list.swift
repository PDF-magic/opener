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

// The initial list never reads bundle paths or executes applications.
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

private struct BrowserDiscoveryLocation: Decodable {
    let bundleIdentifier: String
    let path: String
}

// Convert a fresh, bounded inventory into the same read-only list items.
// Recheck each executable and bundle identity; discovery output alone never
// gives an application permission to open a scanned PDF.
func refreshedBrowserPreferenceItems(
    from data: Data,
    metadataLookup: (URL) -> BrowserApplicationMetadata? = {
        browserApplicationMetadata(at: $0)
    }
) -> [BrowserPreferenceItem]? {
    guard data.count <= 256 * 1024,
          let found = try? JSONDecoder().decode([BrowserDiscoveryLocation].self, from: data),
          found.count <= 2048 else { return nil }

    var identifiers = Set<String>()
    var items = [BrowserPreferenceItem]()
    for location in found {
        guard location.path.hasPrefix("/"),
              location.path.utf8.count <= 4096,
              !location.path.unicodeScalars.contains(where: {
                  CharacterSet.controlCharacters.contains($0)
              }),
              supportedBrowserBundleIDs.contains(location.bundleIdentifier),
              let metadata = metadataLookup(URL(fileURLWithPath: location.path)),
              metadata.bundleIdentifier == location.bundleIdentifier,
              !identifiers.contains(metadata.bundleIdentifier),
              let name = safeBrowserDisplayText(metadata.name, limit: 128) else { continue }

        identifiers.insert(metadata.bundleIdentifier)
        items.append(BrowserPreferenceItem(
            bundleIdentifier: metadata.bundleIdentifier,
            name: name,
            version: metadata.version.flatMap { safeBrowserDisplayText($0, limit: 64) },
            icon: metadata.icon
        ))
        // Match the existing preference-view limit instead of rendering a
        // surprise unbounded list when a discovery provider malfunctions.
        guard items.count <= 100 else { return nil }
    }
    return items
}

// Rerun the installed discovery helper only after an explicit Refresh action.
// No selection, preference file, PDF association, or scan state is touched.
func rediscoverBrowserPreferenceItems(
    executable: URL = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/Studio/allow-and-open/discover-installed-browsers")
) -> [BrowserPreferenceItem]? {
    guard executable.isFileURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else { return nil }
    let process = Process()
    process.executableURL = executable
    process.standardError = FileHandle.nullDevice
    let pipe = Pipe()
    process.standardOutput = pipe
    do {
        try process.run()
    } catch {
        return nil
    }
    // Drain before waiting: a large inventory could otherwise block the
    // discovery process on a full stdout pipe.
    var data = Data()
    let limit = 256 * 1024
    while data.count <= limit {
        let chunk = pipe.fileHandleForReading.readData(
            ofLength: min(65536, limit + 1 - data.count))
        if chunk.isEmpty { break }
        data.append(chunk)
    }
    if data.count > limit && process.isRunning {
        process.terminate()
    }
    process.waitUntilExit()
    guard data.count <= limit, process.terminationStatus == 0 else { return nil }
    return refreshedBrowserPreferenceItems(from: data)
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
        // Explicit input only: never inspect user configuration or select a PDF
        // destination. Callers can aggregate the read-only metadata JSON.
        let input = FileHandle.standardInput.readData(ofLength: 4 * 1024 * 1024 + 1)
        guard let items = browserPreferenceItems(from: input) else {
            fputs("Expected a JSON array of discovered browser metadata.\n", stderr)
            exit(EXIT_FAILURE)
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
                completion(rediscoverBrowserPreferenceItems())
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
