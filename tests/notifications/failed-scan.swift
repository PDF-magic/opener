import Foundation

@main
struct FailedScanNotificationTests {
  static func main() {
    let suiteName = "local.studio.pdf-magic-opener.test.failed." + UUID().uuidString
    guard let defaults = UserDefaults(suiteName: suiteName) else { fatalError("Isolated defaults unavailable") }
    defer { defaults.removePersistentDomain(forName: suiteName) }
    let failed = "Scan request 1: The malware scan could not finish; opening was stopped.\n"
    let incomplete = "Scan request 1: The malware scan did not confirm a complete scan; opening was stopped.\n"
    let timedOut = "Scan request 1: The malware scan timed out; opening was stopped.\n"

    precondition(!BlockedFileNotificationPreference.isEnabled(defaults: defaults))
    precondition(!FailedScanNotificationClassification.shouldShowFailedScanNotice(
      failure: failed, cancelled: false, enabled: false))
    defaults.set("com.example.custom", forKey: "customBrowser")
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    precondition(BlockedFileNotificationPreference.save(true, defaults: defaults))
    let reloaded = UserDefaults(suiteName: suiteName)!
    precondition(BlockedFileNotificationPreference.isEnabled(defaults: reloaded))

    for failure in [failed, incomplete, timedOut,
                    "The malware scan exceeded its execution timeout; opening was stopped.",
                    "The malware scan could not finish.",
                    "The installed scan helper is missing. Reinstall PDF Magic Opener.",
                    "The scan helper could not start. Reinstall PDF Magic Opener."] {
      precondition(FailedScanNotificationClassification.shouldShowFailedScanNotice(
        failure: failure, cancelled: false, enabled: true))
      precondition(!FailedScanNotificationClassification.shouldShowFailedScanNotice(
        failure: failure, cancelled: true, enabled: true))
    }
    for failure in [
      "Scan request 1: Malware was detected; opening was stopped.\n",
      "Scan request 1: The scanner flagged a suspicious or unscannable item; opening was stopped.\n",
      "Scan request 1: The malware scan could not finish; opening was stopped.",
      "Scan request 2: The malware scan could not finish; opening was stopped.\n",
      failed + "/private/report.pdf", "prefix " + failed,
      "Opening failed", "The scan was cancelled; opening was stopped.", ""
    ] {
      precondition(!FailedScanNotificationClassification.shouldShowFailedScanNotice(
        failure: failure, cancelled: false, enabled: true))
    }
    precondition(!FailedScanNotificationClassification.shouldShowFailedScanNotice(
      failure: nil, cancelled: false, enabled: true))
    precondition(ScanProgressPreference.isEnabled(defaults: reloaded))
    precondition(reloaded.bool(forKey: SuccessfulScanNotificationPreference.key))
    precondition(reloaded.string(forKey: "customBrowser") == "com.example.custom")
    precondition(BlockedFileNotificationPreference.save(false, defaults: defaults))
    precondition(!FailedScanNotificationClassification.shouldShowFailedScanNotice(
      failure: failed, cancelled: false,
      enabled: BlockedFileNotificationPreference.isEnabled(defaults: reloaded)))
    print("PASS: failed-scan notifications use exact evidence and opt-in without weakening safety")
  }
}
