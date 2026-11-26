import Foundation

// Pure connection-health presentation. No persistence, permissions or I/O.
@main
struct DownloadConnectionHealthTests {
  static func main() {
    let initial = BrowserNativeConnectionHealth.current
    precondition(initial == .notConnected)
    precondition(initial.statusLabel == "Not connected")
    precondition(initial.detail.contains("No authenticated browser-to-native connection"))
    precondition(!initial.scannerConnectionHealthy)

    let missingAuthentication = BrowserNativeConnectionHealth.fromVerifiedHandshake(
      authenticatedSession: false,
      protocolVersion: 1,
      hostStatus: "transport-only",
      scanAvailable: false
    )
    precondition(missingAuthentication == .notConnected)

    let transport = BrowserNativeConnectionHealth.fromVerifiedHandshake(
      authenticatedSession: true,
      protocolVersion: 1,
      hostStatus: "transport-only",
      scanAvailable: false
    )
    precondition(transport == .transportOnly)
    precondition(transport.statusLabel == "Host reachable — scanning unavailable")
    precondition(!transport.scannerConnectionHealthy)
    precondition(transport.detail.contains("scanner is not connected"))

    for claimedStatus in ["connected", "ready", "scanner-active", "", "transport-only"] {
      let health = BrowserNativeConnectionHealth.fromVerifiedHandshake(
        authenticatedSession: true,
        protocolVersion: 1,
        hostStatus: claimedStatus,
        scanAvailable: true
      )
      precondition(health == .notConnected)
      precondition(!health.scannerConnectionHealthy)
    }
    let wrongVersion = BrowserNativeConnectionHealth.fromVerifiedHandshake(
      authenticatedSession: true,
      protocolVersion: 2,
      hostStatus: "transport-only",
      scanAvailable: false
    )
    precondition(wrongVersion == .notConnected)
    precondition(!wrongVersion.scannerConnectionHealthy)

    // An opt-in setting must not be mistaken for a verified active connection.
    let suite = "local.studio.pdf-magic-opener.health-indicator-test." + UUID().uuidString
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot create isolated preferences")
    }
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(true, forKey: BrowserDownloadMonitoringPreference.key)
    defaults.set("preserve-user-preference", forKey: "customBrowser")
    precondition(BrowserDownloadMonitoringPreference.isEnabled(defaults: defaults))
    precondition(BrowserNativeConnectionHealth.current == .notConnected)
    precondition(defaults.string(forKey: "customBrowser") == "preserve-user-preference")

    print("Connection-health status never asserts unsupported scanner readiness")
  }
}
