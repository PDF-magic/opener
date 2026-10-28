import Foundation

@main
struct ResetGeneralPreferencesTests {
  static func main() {
    let name = "local.studio.pdf-magic-opener.reset-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: name) else { fatalError("No test suite") }
    defer { defaults.removePersistentDomain(forName: name) }
    let progress = ScanProgressPreference.key
    let notifications = SuccessfulScanNotificationPreference.key
    let unrelated = "preferredPDFBrowser"
    defaults.set(false, forKey: progress)
    defaults.set(true, forKey: notifications)
    defaults.set("org.mozilla.firefox", forKey: unrelated)
    precondition(GeneralPreferencesReset.reset(defaults: defaults))
    precondition(defaults.object(forKey: progress) == nil)
    precondition(defaults.object(forKey: notifications) == nil)
    precondition(ScanProgressPreference.isEnabled(defaults: defaults))
    precondition(!SuccessfulScanNotificationPreference.isEnabled(defaults: defaults))
    precondition(defaults.string(forKey: unrelated) == "org.mozilla.firefox")
    // Idempotent reset; other customizations are never removed.
    precondition(GeneralPreferencesReset.reset(defaults: defaults))
    precondition(defaults.string(forKey: unrelated) == "org.mozilla.firefox")
    precondition(!GeneralPreferencesReset.reset(defaults: nil))
    print("General preferences reset tests passed")
  }
}
