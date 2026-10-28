import Foundation

@main
struct ScanProgressPreferenceTests {
  static func main() {
    let name = "local.studio.pdf-magic-opener.test." + UUID().uuidString
    guard let suite = UserDefaults(suiteName: name) else {
      fatalError("Could not create isolated user defaults suite")
    }
    defer { suite.removePersistentDomain(forName: name) }
    suite.removeObject(forKey: ScanProgressPreference.key)

    precondition(ScanProgressPreference.isEnabled(defaults: suite),
                 "Unset option must preserve visible progress and Cancel")
    suite.set("unknown", forKey: ScanProgressPreference.key)
    precondition(ScanProgressPreference.isEnabled(defaults: suite),
                 "Unexpected preference data must default to visible")

    precondition(ScanProgressPreference.save(false, defaults: suite),
                 "Explicit disable should be saved")
    precondition(!ScanProgressPreference.isEnabled(defaults: suite),
                 "Disabled setting must be read back")
    let reopened = UserDefaults(suiteName: name)!
    precondition(!ScanProgressPreference.isEnabled(defaults: reopened),
                 "A separate process using the shared suite must see the selection")

    precondition(ScanProgressPreference.save(true, defaults: suite),
                 "Re-enabling progress must succeed")
    precondition(ScanProgressPreference.isEnabled(defaults: reopened),
                 "Re-enabled setting must persist")
    precondition(ScanProgressPreference.isEnabled(defaults: nil),
                 "Unavailable defaults must retain the safe visible default")
    precondition(!ScanProgressPreference.save(false, defaults: nil),
                 "An unavailable store must never claim success")

    print("PASS: show-scan-progress preference defaults visible and persists explicit choices")
  }
}
