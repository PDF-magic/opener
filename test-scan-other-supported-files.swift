import Foundation
import CoreFoundation

// Test the real shared preference implementation in a disposable domain.
// A browser integration is not present and none of these operations scan.
@main
struct ScanOtherSupportedFilesTests {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.other-files-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot create isolated preferences domain")
    }
    defer {
      defaults.removePersistentDomain(forName: suite)
      _ = defaults.synchronize()
    }

    // Existing installations must not silently start monitoring non-PDF files.
    precondition(defaults.object(forKey: ScanOtherSupportedFilesPreference.key) == nil)
    precondition(!ScanOtherSupportedFilesPreference.isEnabled(defaults: defaults))
    defaults.set("preserve", forKey: "customBrowser")
    defaults.set("future-value", forKey: "futureSetting")
    defaults.set(false, forKey: ScanProgressPreference.key)
    precondition(ScanOtherSupportedFilesPreference.save(true, defaults: defaults))
    precondition(ScanOtherSupportedFilesPreference.isEnabled(defaults: defaults))
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(ScanOtherSupportedFilesPreference.isEnabled(defaults: defaults))

    // Recreate the defaults reader to model settings reload and user relaunch.
    guard let reopened = UserDefaults(suiteName: suite) else {
      fatalError("Cannot reopen preferences domain")
    }
    precondition(ScanOtherSupportedFilesPreference.isEnabled(defaults: reopened))
    precondition(ScanOtherSupportedFilesPreference.save(false, defaults: reopened))
    precondition(!ScanOtherSupportedFilesPreference.isEnabled(defaults: defaults))

    // Invalid stored values are not treated as consent or repaired on read.
    defaults.set("true", forKey: ScanOtherSupportedFilesPreference.key)
    precondition(!ScanOtherSupportedFilesPreference.isEnabled(defaults: defaults))
    precondition(defaults.string(forKey: ScanOtherSupportedFilesPreference.key) == "true")
    defaults.set(1, forKey: ScanOtherSupportedFilesPreference.key)
    precondition(!ScanOtherSupportedFilesPreference.isEnabled(defaults: defaults))
    precondition(!ScanOtherSupportedFilesPreference.save(true, defaults: nil))
    precondition(ScanOtherSupportedFilesPreference.save(true, defaults: defaults))

    // An explicit update must change only this key, never scanner or user choices.
    precondition(ScanOtherSupportedFilesPreference.isEnabled(defaults: defaults))
    precondition(defaults.string(forKey: "customBrowser") == "preserve")
    precondition(defaults.string(forKey: "futureSetting") == "future-value")
    precondition(!ScanProgressPreference.isEnabled(defaults: defaults))
    precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn)
    print("Opt-in scope is isolated, persists, and fails closed on malformed values")
  }
}
