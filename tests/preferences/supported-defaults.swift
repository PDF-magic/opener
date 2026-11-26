import Foundation

// Use an isolated volatile domain; never alter a user's installed preferences.
@main
struct TestSupportedPreferenceDefaults {
 static func main() {
let suite = "local.studio.pdf-magic-opener.defaults-test.\(UUID().uuidString)"
guard let defaults = UserDefaults(suiteName: suite) else {
  fatalError("Could not create isolated preferences")
}
defer { defaults.removePersistentDomain(forName: suite) }

assert(SupportedPreferenceDefaults.showScanProgress)
assert(!SupportedPreferenceDefaults.showSuccessfulScanNotifications)
assert(SupportedPreferenceDefaults.pdfBrowserBundleIdentifier == "com.brave.Browser")
assert(ScanProgressPreference.isEnabled(defaults: defaults))
assert(!SuccessfulScanNotificationPreference.isEnabled(defaults: defaults))

defaults.set(false, forKey: ScanProgressPreference.key)
defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
defaults.set("custom-preference", forKey: "unrelatedPreference")
assert(!ScanProgressPreference.isEnabled(defaults: defaults))
assert(SuccessfulScanNotificationPreference.isEnabled(defaults: defaults))
assert(defaults.string(forKey: "unrelatedPreference") == "custom-preference")

defaults.removeObject(forKey: ScanProgressPreference.key)
defaults.removeObject(forKey: SuccessfulScanNotificationPreference.key)
assert(ScanProgressPreference.isEnabled(defaults: defaults))
assert(!SuccessfulScanNotificationPreference.isEnabled(defaults: defaults))
assert(defaults.string(forKey: "unrelatedPreference") == "custom-preference")

print("Supported preference defaults and saved user overrides verified")

 }
}
