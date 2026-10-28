import Foundation

// A cosmetic setting shared by the standalone preferences UI and the
// separately installed PDF scan handler. It does not change scan policy.
// Defaults for every currently configurable preference. No registration or
// persistence is performed here: absent keys use these values, while existing
// user overrides remain authoritative. Scanner safety controls are not settings.
enum SupportedPreferenceDefaults {
  static let showScanProgress = true
  static let showSuccessfulScanNotifications = false
  static let pdfBrowserBundleIdentifier = "com.brave.Browser"
}

enum ScanProgressPreference {
  static let suiteName = "local.studio.pdf-magic-opener"
  static let key = "showScanProgress"

  // Existing installations have no saved value: preserve the visible
  // progress window (and its Cancel action) by default.
  static func isEnabled(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults,
          let setting = defaults.object(forKey: key) as? Bool else {
      return SupportedPreferenceDefaults.showScanProgress
    }
    return setting
  }

  @discardableResult
  static func save(
    _ enabled: Bool,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    defaults.set(enabled, forKey: key)
    return defaults.synchronize() && isEnabled(defaults: defaults) == enabled
  }
}


// Opt-in presentation only: the scan gate never consults this setting.
// The same suite is readable by the separately installed PDF opener.
enum SuccessfulScanNotificationPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "showSuccessfulScanNotifications"

  // No existing success alerts: keep them disabled until the user opts in.
  static func isEnabled(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults,
          let setting = defaults.object(forKey: key) as? Bool else {
      return SupportedPreferenceDefaults.showSuccessfulScanNotifications
    }
    return setting
  }

  @discardableResult
  static func save(
    _ enabled: Bool,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    defaults.set(enabled, forKey: key)
    return defaults.synchronize() && isEnabled(defaults: defaults) == enabled
  }

  // Only a completed native request with a zero exit status may
  // produce a success notification. A cancelled process returns nil as its
  // failure message, so cancellation MUST be checked independently.
  static func shouldNotify(
    failure: String?,
    cancelled: Bool,
    enabled: Bool = isEnabled()
  ) -> Bool {
    return enabled && failure == nil && !cancelled
  }
}
