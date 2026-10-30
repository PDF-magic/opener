import Foundation
import CoreFoundation

// Verify the compiled preference contract with a disposable UserDefaults suite.
// Never access or reset the real PDF Magic Opener preferences domain.
@main
struct DownloadScanResultsTests {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.scan-results-test." + UUID().uuidString
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot create isolated preference domain")
    }
    defer { defaults.removePersistentDomain(forName: suite) }
    let key = DownloadScanResultsPreference.key

    // Preserve existing visibility unless a user explicitly disables it.
    precondition(DownloadScanResultsPreference.isEnabled(defaults: defaults))
    precondition(defaults.object(forKey: key) == nil)
    defaults.set("false", forKey: key)
    precondition(DownloadScanResultsPreference.isEnabled(defaults: defaults))
    defaults.set(0, forKey: key)
    precondition(DownloadScanResultsPreference.isEnabled(defaults: defaults))
    defaults.removeObject(forKey: key)

    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set("keep-custom-target", forKey: "unrelatedBrowserPreference")
    precondition(DownloadScanResultsPreference.save(false, defaults: defaults))
    let reopened = UserDefaults(suiteName: suite)!
    precondition(!DownloadScanResultsPreference.isEnabled(defaults: reopened))
    precondition(!DownloadScanResultsPreference.shouldPresent(.optionalSummary, defaults: reopened))
    precondition(DownloadScanResultsPreference.shouldPresent(.securityWarning, defaults: reopened))

    precondition(DownloadScanResultsPreference.save(true, defaults: defaults))
    precondition(DownloadScanResultsPreference.isEnabled(defaults: reopened))
    precondition(DownloadScanResultsPreference.shouldPresent(.optionalSummary, defaults: reopened))
    precondition(DownloadScanResultsPreference.shouldPresent(.securityWarning, defaults: reopened))
    precondition(!ScanProgressPreference.isEnabled(defaults: defaults))
    precondition(defaults.string(forKey: "unrelatedBrowserPreference") == "keep-custom-target")
    precondition(!DownloadScanResultsPreference.save(false, defaults: nil))
    precondition(DownloadScanResultsPreference.isEnabled(defaults: nil))
    print("Show Scan Results preference and mandatory warning visibility verified")
  }
}
