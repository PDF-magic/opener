import Foundation
import CoreFoundation

// All writes are to an isolated, disposable suite; never touch live settings.
@main
struct NotifyOnFailedScanTests {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.failed-scan-test." + UUID().uuidString
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot create isolated defaults suite")
    }
    defer { defaults.removePersistentDomain(forName: suite) }
    let key = DownloadFailedScanNotificationPreference.key

    precondition(!DownloadFailedScanNotificationPreference.isEnabled(defaults: defaults))
    precondition(defaults.object(forKey: key) == nil)
    for outcome in [DownloadScanNotificationOutcome.failed, .incomplete, .clean, .blocked, .cancelled, .unknown] {
      precondition(!DownloadFailedScanNotificationPreference.shouldNotify(outcome, defaults: defaults))
    }

    defaults.set("true", forKey: key)
    precondition(!DownloadFailedScanNotificationPreference.isEnabled(defaults: defaults))
    defaults.set(1, forKey: key)
    precondition(!DownloadFailedScanNotificationPreference.isEnabled(defaults: defaults))
    defaults.set("preserve-browser", forKey: "customBrowser")
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: BlockedFileNotificationPreference.key)
    defaults.set(true, forKey: DownloadWarningOnlyPreference.key)
    defaults.set(true, forKey: BrowserDownloadMonitoringPreference.key)

    // Explicit opt-in converts only this malformed integer setting to a Bool.
    precondition(DownloadFailedScanNotificationPreference.save(true, defaults: defaults))
    let reloaded = UserDefaults(suiteName: suite)!
    precondition(DownloadFailedScanNotificationPreference.isEnabled(defaults: reloaded))
    precondition(DownloadFailedScanNotificationPreference.shouldNotify(.failed, defaults: reloaded))
    precondition(DownloadFailedScanNotificationPreference.shouldNotify(.incomplete, defaults: reloaded))
    for outcome in [DownloadScanNotificationOutcome.clean, .blocked, .cancelled, .unknown] {
      precondition(!DownloadFailedScanNotificationPreference.shouldNotify(outcome, defaults: reloaded))
    }

    precondition(reloaded.string(forKey: "customBrowser") == "preserve-browser")
    precondition(!ScanProgressPreference.isEnabled(defaults: reloaded))
    precondition(BlockedFileNotificationPreference.isEnabled(defaults: reloaded))
    precondition(DownloadWarningOnlyPreference.isEnabled(defaults: reloaded))
    precondition(BrowserDownloadMonitoringPreference.isEnabled(defaults: reloaded))

    precondition(DownloadFailedScanNotificationPreference.save(false, defaults: defaults))
    precondition(!DownloadFailedScanNotificationPreference.isEnabled(defaults: reloaded))
    precondition(!DownloadFailedScanNotificationPreference.shouldNotify(.failed, defaults: reloaded))
    precondition(!DownloadFailedScanNotificationPreference.save(true, defaults: nil))
    precondition(!DownloadFailedScanNotificationPreference.isEnabled(defaults: nil))
    precondition(!DownloadFailedScanNotificationPreference.shouldNotify(.failed, defaults: nil))
    print("Notify on Failed Scan is opt-in, isolated and preserves mandatory alerts")
  }
}
