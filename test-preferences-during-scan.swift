import Foundation

// A separate process exercises the same preference APIs as GeneralSettingsView.
// Only a unique throwaway suite is changed; scanner and user settings are untouched.
@main
struct PreferencesDuringScanDriver {
  static func main() {
    precondition(CommandLine.arguments.count == 3, "Expected action and test suite")
    let action = CommandLine.arguments[1]
    let name = CommandLine.arguments[2]
    precondition(name.hasPrefix("local.studio.pdf-magic-opener.active-scan-test."),
                 "Refusing to write a non-test preferences suite")
    guard let defaults = UserDefaults(suiteName: name) else {
      fatalError("Could not create test preferences suite")
    }
    let unrelated = "unrelatedCustomization"

    switch action {
    case "seed":
      defaults.removePersistentDomain(forName: name)
      defaults.set("preserve-my-choice", forKey: unrelated)
      precondition(ScanProgressPreference.save(true, defaults: defaults))
      precondition(SuccessfulScanNotificationPreference.save(false, defaults: defaults))
      precondition(BlockedFileNotificationPreference.save(false, defaults: defaults))
    case "edit":
      precondition(ScanProgressPreference.save(false, defaults: defaults))
      precondition(SuccessfulScanNotificationPreference.save(true, defaults: defaults))
      precondition(BlockedFileNotificationPreference.save(true, defaults: defaults))
    case "verify":
      precondition(!ScanProgressPreference.isEnabled(defaults: defaults),
                   "A progress change made during scanning must persist")
      precondition(SuccessfulScanNotificationPreference.isEnabled(defaults: defaults),
                   "The success notification selection must persist")
      precondition(BlockedFileNotificationPreference.isEnabled(defaults: defaults),
                   "The blocked notification selection must persist")
      precondition(defaults.string(forKey: unrelated) == "preserve-my-choice",
                   "Unrelated user customizations must be preserved")
    case "cleanup":
      defaults.removePersistentDomain(forName: name)
      precondition(defaults.synchronize(), "Test suite cleanup failed")
    default:
      fatalError("Unknown test driver action")
    }
  }
}
