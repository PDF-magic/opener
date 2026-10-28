import AppKit
import Foundation

// A preferences window is allowed to display a changing browser inventory,
// but never to write the user's selected PDF application or launch a file.
// Re-read discovery while the window remains open; an install or removal is not
// guaranteed to emit an NSWorkspace application launch notification.
struct BrowserPreferenceFingerprint: Equatable {
    struct Entry: Equatable {
        let bundleIdentifier: String
        let name: String
        let version: String?
    }
    let entries: [Entry]

    init(items: [BrowserPreferenceItem]) {
        entries = items.map {
            Entry(bundleIdentifier: $0.bundleIdentifier, name: $0.name, version: $0.version)
        }
    }
}

final class BrowserPreferenceLiveRefresher {
    private let discover: () -> [BrowserPreferenceItem]
    private let update: ([BrowserPreferenceItem]) -> Void
    private var fingerprint: BrowserPreferenceFingerprint
    private(set) var timer: Timer?

    init(initialItems: [BrowserPreferenceItem],
         discover: @escaping () -> [BrowserPreferenceItem],
         update: @escaping ([BrowserPreferenceItem]) -> Void) {
        self.discover = discover
        self.update = update
        fingerprint = BrowserPreferenceFingerprint(items: initialItems)
    }

    @discardableResult
    func refreshIfChanged() -> Bool {
        let items = discover()
        let next = BrowserPreferenceFingerprint(items: items)
        guard next != fingerprint else { return false }
        fingerprint = next
        update(items)
        return true
    }

    // Scan only while the settings window is open. A periodic reconciliation
    // also catches applications on external/custom paths and missing folders
    // that later become available; unlike one-off launch notifications it
    // detects both installations and removals.
    func start(interval: TimeInterval = 5) {
        stop()
        timer = Timer.scheduledTimer(withTimeInterval: max(0.1, interval),
                                     repeats: true) { [weak self] _ in
            self?.refreshIfChanged()
        }
    }

    func stop() {
        timer?.invalidate()
        timer = nil
    }

    deinit {
        stop()
    }
}
