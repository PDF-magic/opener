import Foundation

// A cosmetic setting shared by the standalone preferences UI and the
// separately installed PDF scan handler. It does not change scan policy.
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
      return true
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
      return false
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

// Optional blocked-open alert delivery; scanner verdicts and warnings never depend on it.
enum BlockedFileNotificationPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "showBlockedFileNotifications"

  static func isEnabled(defaults: UserDefaults? = UserDefaults(suiteName: suiteName)) -> Bool {
    guard let defaults, let setting = defaults.object(forKey: key) as? Bool else { return false }
    return setting
  }

  @discardableResult
  static func save(_ enabled: Bool, defaults: UserDefaults? = UserDefaults(suiteName: suiteName)) -> Bool {
    guard let defaults else { return false }
    defaults.set(enabled, forKey: key)
    return defaults.synchronize() && isEnabled(defaults: defaults) == enabled
  }

  static func shouldNotify(failure: String?, cancelled: Bool, enabled: Bool = isEnabled()) -> Bool {
    return enabled && failure != nil && !cancelled
  }
}

// General reset is intentionally limited to presentation preferences. Removing
// overrides restores their documented defaults without touching any PDF target,
// Launch Services association, malware scanner configuration or unrelated keys.
enum GeneralPreferencesReset {
  static func reset(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    let keys = [ScanProgressPreference.key, SuccessfulScanNotificationPreference.key, BlockedFileNotificationPreference.key]
    let previous = keys.map { defaults.object(forKey: $0) }
    for key in keys { defaults.removeObject(forKey: key) }
    if defaults.synchronize() &&
        keys.allSatisfy({ defaults.object(forKey: $0) == nil }) {
      return true
    }
    // Best effort rollback if persistence fails, instead of reporting success.
    for (key, value) in zip(keys, previous) {
      if let value { defaults.set(value, forKey: key) }
      else { defaults.removeObject(forKey: key) }
    }
    _ = defaults.synchronize()
    return false
  }
}
