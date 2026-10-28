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
        let url = URL(fileURLWithPath: browser.path)
        guard url.pathExtension.lowercased() == "app",
              let details = metadata(url),
              details.bundleIdentifier == browser.bundleIdentifier,
              details.bundleURL.standardizedFileURL.resolvingSymlinksInPath()
                  == url.standardizedFileURL.resolvingSymlinksInPath(),
              let name = safeBrowserDisplayText(details.name, limit: 128),
              browser.bundleIdentifier != "local.studio.brave-pdf-opener",
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
    let nameField: NSTextField
    let iconView: NSImageView
    let versionField: NSTextField?
    let detailsButton: NSButton?

    init(item: BrowserPreferenceItem) {
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

final class BrowserPreferenceListView: NSStackView {
    let rows: [BrowserPreferenceRow]

    init(items: [BrowserPreferenceItem]) {
        rows = items.map { BrowserPreferenceRow(item: $0) }
        super.init(frame: .zero)
        orientation = .vertical
        alignment = .leading
        spacing = 12
        if rows.isEmpty {
            addArrangedSubview(NSTextField(labelWithString: "No discovered browsers to display."))
        } else {
            rows.forEach { addArrangedSubview($0) }
        }
    }

    required init?(coder: NSCoder) { return nil }
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

        let list = BrowserPreferenceListView(items: items)
        let contentHeight = max(120, CGFloat(max(items.count, 1)) * 84 + 32)
        let document = NSView(frame: NSRect(x: 0, y: 0, width: 520, height: contentHeight))
        list.frame = NSRect(x: 16, y: 16, width: 488, height: contentHeight - 32)
        document.addSubview(list)

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
