import Foundation
import CoreFoundation

// Isolated UserDefaults suite; never read, migrate or reset the user's domain.
@main
struct ShowOnlyWarningsTests {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.warning-test." + UUID().uuidString
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot create isolated defaults suite")
    }
    defer { defaults.removePersistentDomain(forName: suite) }

    let key = DownloadWarningOnlyPreference.key
    precondition(!DownloadWarningOnlyPreference.isEnabled(defaults: defaults))
    precondition(defaults.object(forKey: key) == nil)
    precondition(DownloadWarningOnlyPreference.shouldPresent(.verifiedCleanSummary, defaults: defaults))
    precondition(DownloadWarningOnlyPreference.shouldPresent(.verifiedInformationalSummary, defaults: defaults))
    for kind in [DownloadWarningDisplayKind.securityWarning, .scanIncompleteOrFailed, .unknown] {
      precondition(DownloadWarningOnlyPreference.shouldPresent(kind, defaults: defaults))
    }

    // A corrupt or unexpected value must not silently hide warnings or summaries.
    defaults.set("true", forKey: key)
    precondition(!DownloadWarningOnlyPreference.isEnabled(defaults: defaults))
    defaults.set(1, forKey: key)
    precondition(!DownloadWarningOnlyPreference.isEnabled(defaults: defaults))
    defaults.removeObject(forKey: key)

    defaults.set("keep-custom-browser", forKey: "preferredBrowser")
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: BlockedFileNotificationPreference.key)
    precondition(DownloadWarningOnlyPreference.save(true, defaults: defaults))
    let reloaded = UserDefaults(suiteName: suite)!
    precondition(DownloadWarningOnlyPreference.isEnabled(defaults: reloaded))
    precondition(!DownloadWarningOnlyPreference.shouldPresent(.verifiedCleanSummary, defaults: reloaded))
    precondition(!DownloadWarningOnlyPreference.shouldPresent(.verifiedInformationalSummary, defaults: reloaded))
    for kind in [DownloadWarningDisplayKind.securityWarning, .scanIncompleteOrFailed, .unknown] {
      precondition(DownloadWarningOnlyPreference.shouldPresent(kind, defaults: reloaded))
    }
    precondition(reloaded.string(forKey: "preferredBrowser") == "keep-custom-browser")
    precondition(!ScanProgressPreference.isEnabled(defaults: reloaded))
    precondition(BlockedFileNotificationPreference.isEnabled(defaults: reloaded))

    precondition(DownloadWarningOnlyPreference.save(false, defaults: defaults))
    precondition(!DownloadWarningOnlyPreference.isEnabled(defaults: reloaded))
    precondition(DownloadWarningOnlyPreference.shouldPresent(.verifiedCleanSummary, defaults: reloaded))
    precondition(!DownloadWarningOnlyPreference.save(true, defaults: nil))
    precondition(!DownloadWarningOnlyPreference.isEnabled(defaults: nil))
    precondition(DownloadWarningOnlyPreference.shouldPresent(.securityWarning, defaults: nil))
    print("Show Only Warnings preference and mandatory safety notices verified")
  }
}
