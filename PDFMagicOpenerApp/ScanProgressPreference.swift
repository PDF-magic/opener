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

// Create persisted presentation preferences on first launch without overwriting
// user choices. The installed scanner continues to own its separate settings.
enum InitialConfiguration {
  @discardableResult
  static func createIfNeeded(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    // Persist and validate the active schema before initializing settings.
    // Never rewrite preferences associated with incompatible version metadata.
    guard ActiveConfigurationSchemaVersion.recordIfNeeded(defaults: defaults) else { return false }
    if defaults.object(forKey: ScanProgressPreference.key) == nil {
      defaults.set(SupportedPreferenceDefaults.showScanProgress, forKey: ScanProgressPreference.key)
    }
    if defaults.object(forKey: SuccessfulScanNotificationPreference.key) == nil {
      defaults.set(SupportedPreferenceDefaults.showSuccessfulScanNotifications, forKey: SuccessfulScanNotificationPreference.key)
    }
    if defaults.object(forKey: BlockedFileNotificationPreference.key) == nil {
      defaults.set(false, forKey: BlockedFileNotificationPreference.key)
    }
    return defaults.synchronize()
  }
}

// Record the schema version in the same shared defaults suite as the active
// preferences. This metadata does not migrate or reset any user setting.
enum ActiveConfigurationSchemaVersion {
  static let key = "schemaVersion"

  static func read(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Int? {
    guard let defaults, let version = defaults.object(forKey: key) as? Int,
          version > 0 else { return nil }
    return version
  }

  @discardableResult
  static func recordIfNeeded(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    if defaults.object(forKey: key) != nil {
      // Keep future, older and malformed values intact; refuse silent migration.
      return read(defaults: defaults) == PDFMagicConfigurationSchema.currentVersion
    }
    defaults.set(PDFMagicConfigurationSchema.currentVersion, forKey: key)
    return defaults.synchronize() &&
      read(defaults: defaults) == PDFMagicConfigurationSchema.currentVersion
  }
}

// Versioned, opt-in representation for settings shared by the preferences app
// and the installed opener. This defines a future persistence contract; it does
// not migrate or overwrite the existing UserDefaults keys on its own.
// Nil means "not explicitly configured", preserving each setting's legacy default.
struct PDFMagicConfigurationSchema: Codable, Equatable {
  static let currentVersion = 1

  let schemaVersion: Int
  var showScanProgress: Bool?
  var showSuccessfulScanNotifications: Bool?
  var showBlockedFileNotifications: Bool?

  init(
    showScanProgress: Bool? = nil,
    showSuccessfulScanNotifications: Bool? = nil,
    showBlockedFileNotifications: Bool? = nil
  ) {
    schemaVersion = Self.currentVersion
    self.showScanProgress = showScanProgress
    self.showSuccessfulScanNotifications = showSuccessfulScanNotifications
    self.showBlockedFileNotifications = showBlockedFileNotifications
  }

  private enum CodingKeys: String, CodingKey {
    case schemaVersion
    case showScanProgress
    case showSuccessfulScanNotifications
    case showBlockedFileNotifications
  }

  init(from decoder: Decoder) throws {
    let values = try decoder.container(keyedBy: CodingKeys.self)
    let version = try values.decode(Int.self, forKey: .schemaVersion)
    guard version == Self.currentVersion else {
      throw DecodingError.dataCorruptedError(
        forKey: .schemaVersion,
        in: values,
        debugDescription: "Unsupported configuration schema version"
      )
    }
    schemaVersion = version
    showScanProgress = try values.decodeIfPresent(Bool.self, forKey: .showScanProgress)
    showSuccessfulScanNotifications = try values.decodeIfPresent(
      Bool.self, forKey: .showSuccessfulScanNotifications
    )
    showBlockedFileNotifications = try values.decodeIfPresent(Bool.self, forKey: .showBlockedFileNotifications)
  }

  func encoded() throws -> Data {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    return try encoder.encode(self)
  }

  static func decoded(from data: Data) throws -> Self {
    return try JSONDecoder().decode(Self.self, from: data)
  }
}
