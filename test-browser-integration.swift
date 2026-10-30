import Foundation

// Pure read-only local preflight. No simulated native handshake or permission
// changes can make this produce a successful browser integration claim.
@main
struct TestBrowserIntegration {
  static func main() {
    let supported: Set<String> = [
      "com.brave.Browser", "com.google.Chrome", "org.mozilla.firefox"
    ]
    let none = BrowserIntegrationTest.run(supportedIDs: supported, detectedIDs: [])
    precondition(none.detectedCount == 0)
    precondition(none.supportedCount == 3)
    precondition(none.statusLabel == "Integration test unavailable")
    precondition(none.detail.contains("Detected 0 of 3 supported browsers"))
    precondition(none.detail.contains("cannot verify downloads"))

    let some = BrowserIntegrationTest.run(
      supportedIDs: supported, detectedIDs: [
        "com.brave.Browser", "com.google.Chrome", "com.invalid.Unrecognized"
      ]
    )
    precondition(some.detectedCount == 2)
    precondition(some.supportedCount == 3)
    precondition(some.statusLabel == "Integration test unavailable")
    let all = BrowserIntegrationTest.run(supportedIDs: supported, detectedIDs: supported)
    precondition(all.detectedCount == 3)
    precondition(all.statusLabel == "Integration test unavailable")
    let empty = BrowserIntegrationTest.run(supportedIDs: [], detectedIDs: supported)
    precondition(empty.detectedCount == 0 && empty.supportedCount == 0)
    let malformed = BrowserIntegrationTest.run(supportedIDs: ["", "com.brave.Browser"], detectedIDs: [""])
    precondition(malformed.detectedCount == 0 && malformed.supportedCount == 1)

    // A saved monitoring opt-in is deliberately not an input to the result.
    let suite = "local.studio.pdf-magic-opener.integration-test." + UUID().uuidString
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Could not create isolated settings")
    }
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set("preserve-target", forKey: "customPDFBrowser")
    let before = all
    precondition(BrowserDownloadMonitoringPreference.save(true, defaults: defaults))
    precondition(BrowserIntegrationTest.run(supportedIDs: supported, detectedIDs: supported) == before)
    precondition(defaults.string(forKey: "customPDFBrowser") == "preserve-target")
    precondition(defaults.object(forKey: ScanProgressPreference.key) == nil)

    print("Test Browser Integration stays an honest local discovery diagnostic")
  }
}
