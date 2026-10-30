import Foundation
import CoreFoundation

// Use a disposable suite. Never modify the user's installed preferences.
@main
struct TestBrowserDownloadMonitoringPreference {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.download-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Missing isolated defaults")
    }
    defer { defaults.removePersistentDomain(forName: suite) }

    assert(!BrowserDownloadMonitoringPreference.isEnabled(defaults: defaults))
    assert(defaults.object(forKey: BrowserDownloadMonitoringPreference.key) == nil)
    defaults.set("true", forKey: BrowserDownloadMonitoringPreference.key)
    assert(!BrowserDownloadMonitoringPreference.isEnabled(defaults: defaults))
    defaults.set(1, forKey: BrowserDownloadMonitoringPreference.key)
    assert(!BrowserDownloadMonitoringPreference.isEnabled(defaults: defaults))
    defaults.removeObject(forKey: BrowserDownloadMonitoringPreference.key)
    defaults.set("keep-me", forKey: "unrelatedPreference")
    defaults.set(false, forKey: ScanProgressPreference.key)

    assert(BrowserDownloadMonitoringPreference.save(true, defaults: defaults))
    assert(BrowserDownloadMonitoringPreference.isEnabled(defaults: defaults))
    // Reopen the preference domain to test persistence across UI lifecycles.
    let reopened = UserDefaults(suiteName: suite)
    assert(BrowserDownloadMonitoringPreference.isEnabled(defaults: reopened))
    assert(BrowserDownloadMonitoringPreference.save(false, defaults: defaults))
    assert(!BrowserDownloadMonitoringPreference.isEnabled(defaults: reopened))
    assert(!ScanProgressPreference.isEnabled(defaults: defaults))
    assert(defaults.string(forKey: "unrelatedPreference") == "keep-me")
    assert(!BrowserDownloadMonitoringPreference.save(true, defaults: nil))
    print("Browser download monitoring opt-in preference verified")
  }
}
