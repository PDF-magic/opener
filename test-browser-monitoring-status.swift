import Foundation

// All statuses are projections of existing verified discovery; they do not
// read preferences, activate extensions, or authorize scanner/opening work.
@main
struct BrowserMonitoringStatusTests {
  static func main() {
    let supported = [
      (id: "com.brave.Browser", name: "Brave"),
      (id: "org.mozilla.firefox", name: "Firefox"),
      (id: "com.apple.Safari", name: "Safari"),
      (id: "com.brave.Browser", name: "Duplicate"),
      (id: "", name: "Invalid")
    ]
    let detected = Set(["com.brave.Browser", "org.mozilla.firefox", "unrecognized"])
    let rows = BrowserMonitoringStatusDisplay.rows(
      supported: supported, detectedIDs: detected
    )
    precondition(rows.map(\.id) == [
      "com.brave.Browser", "org.mozilla.firefox", "com.apple.Safari"
    ])
    precondition(rows.map(\.statusLabel) == [
      "Not connected", "Not connected", "Not detected"
    ])
    precondition(rows.map(\.name) == ["Brave", "Firefox", "Safari"])
    precondition(BrowserMonitoringStatusDisplay.rows(
      supported: supported, detectedIDs: []
    ).allSatisfy { $0.statusLabel == "Not detected" })
    precondition(BrowserMonitoringStatusDisplay.rows(
      supported: [], detectedIDs: detected
    ).isEmpty)

    // An enabled global opt-in cannot be turned into a per-browser status.
    let suiteName = "local.studio.pdf-magic-opener.browser-status.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else {
      fatalError("Could not create isolated test preferences")
    }
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let before = rows.map(\.statusLabel)
    precondition(BrowserDownloadMonitoringPreference.save(true, defaults: defaults))
    precondition(BrowserDownloadMonitoringPreference.isEnabled(defaults: defaults))
    precondition(BrowserMonitoringStatusDisplay.rows(
      supported: supported, detectedIDs: detected
    ).map(\.statusLabel) == before)
    precondition(defaults.object(forKey: ScanProgressPreference.key) == nil)
    precondition(BrowserDownloadMonitoringPreference.save(false, defaults: defaults))
    precondition(BrowserMonitoringStatusDisplay.rows(
      supported: supported, detectedIDs: detected
    ).map(\.statusLabel) == before)
    print("PASS: browser statuses remain read-only and never claim monitoring is active")
  }
}
