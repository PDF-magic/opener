import Foundation

@main
struct SuccessfulScanNotificationTests {
  static func main() {
    let suiteName = "local.studio.pdf-magic-opener.test.success." + UUID().uuidString
    guard let suite = UserDefaults(suiteName: suiteName) else {
      fatalError("Could not make isolated defaults")
    }
    defer { suite.removePersistentDomain(forName: suiteName) }
    suite.removeObject(forKey: SuccessfulScanNotificationPreference.key)

    precondition(!SuccessfulScanNotificationPreference.isEnabled(defaults: suite),
                 "Existing installations must never turn on success alerts automatically")
    suite.set("unexpected", forKey: SuccessfulScanNotificationPreference.key)
    precondition(!SuccessfulScanNotificationPreference.isEnabled(defaults: suite),
                 "Malformed saved preference must remain off")
    precondition(!SuccessfulScanNotificationPreference.shouldNotify(
      failure: nil, cancelled: false, enabled: false
    ), "Disabled success notifications must not be sent")

    precondition(SuccessfulScanNotificationPreference.save(true, defaults: suite))
    let reopened = UserDefaults(suiteName: suiteName)!
    precondition(SuccessfulScanNotificationPreference.isEnabled(defaults: reopened),
                 "The installed handler must see an explicitly opted-in preference")
    precondition(SuccessfulScanNotificationPreference.shouldNotify(
      failure: nil, cancelled: false, enabled: true
    ), "An explicitly opted-in clean scan and successful handoff may notify")
    precondition(!SuccessfulScanNotificationPreference.shouldNotify(
      failure: "Malware detected", cancelled: false, enabled: true
    ), "Unsafe or failed scans must never notify success")
    precondition(!SuccessfulScanNotificationPreference.shouldNotify(
      failure: "Opening failed", cancelled: false, enabled: true
    ), "Failed handoff must never notify success")
    precondition(!SuccessfulScanNotificationPreference.shouldNotify(
      failure: nil, cancelled: true, enabled: true
    ), "A cancelled scan with no error string must never notify success")
    precondition(SuccessfulScanNotificationPreference.save(false, defaults: suite))
    precondition(!SuccessfulScanNotificationPreference.isEnabled(defaults: reopened))
    precondition(!SuccessfulScanNotificationPreference.isEnabled(defaults: nil))
    precondition(!SuccessfulScanNotificationPreference.save(true, defaults: nil))
    precondition(ScanProgressPreference.isEnabled(defaults: suite),
                 "Notification settings must not change scan progress defaults")
    print("PASS: success notifications opt-in only, persist safely and reject failures/cancellations")
  }
}
