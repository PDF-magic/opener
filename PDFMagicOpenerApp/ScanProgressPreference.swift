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
    // Read changes from other running processes before choosing presentation.
    _ = defaults?.synchronize()
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
    _ = defaults?.synchronize()
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
    _ = defaults?.synchronize()
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

// A read-only effective view shared by the preferences app and native PDF
// opener. Each setting uses the same per-user domain, defaults and validation.
// It cannot modify a scanner verdict or any persisted configuration.
struct EffectivePresentationConfiguration: Equatable {
  let showScanProgress: Bool
  let showSuccessfulScanNotifications: Bool
  let showBlockedFileNotifications: Bool

  static func read(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Self {
    return Self(
      showScanProgress: ScanProgressPreference.isEnabled(defaults: defaults),
      showSuccessfulScanNotifications: SuccessfulScanNotificationPreference.isEnabled(defaults: defaults),
      showBlockedFileNotifications: BlockedFileNotificationPreference.isEnabled(defaults: defaults)
    )
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
    var initializedMissingSetting = false
    if defaults.object(forKey: ScanProgressPreference.key) == nil {
      defaults.set(SupportedPreferenceDefaults.showScanProgress, forKey: ScanProgressPreference.key)
      initializedMissingSetting = true
    }
    if defaults.object(forKey: SuccessfulScanNotificationPreference.key) == nil {
      defaults.set(SupportedPreferenceDefaults.showSuccessfulScanNotifications, forKey: SuccessfulScanNotificationPreference.key)
      initializedMissingSetting = true
    }
    if defaults.object(forKey: BlockedFileNotificationPreference.key) == nil {
      defaults.set(false, forKey: BlockedFileNotificationPreference.key)
      initializedMissingSetting = true
    }
    // A relaunch or an in-place upgrade must not re-save already persisted
    // preferences. Only the first creation of missing keys needs a flush.
    return !initializedMissingSetting || defaults.synchronize()
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

import CoreFoundation

// Explicit, in-memory upgrades for legacy preference snapshots. This does not
// read or write the live preference domain, scanner files, or chosen PDF viewer.
enum PDFMagicConfigurationMigration {
  enum Failure: Error {
    case invalidRoot
    case invalidVersion
    case invalidLegacyValue(String)
  }

  // Version 0 is the pre-schema JSON representation of the same presentation
  // keys; a missing version is accepted only on this explicit migration path.
  // Current-version data is returned byte-for-byte; unknown additive keys are
  // retained when upgrading, rather than discarding future customizations.
  static func migrate(_ data: Data) throws -> Data {
    let decoded = try JSONSerialization.jsonObject(with: data)
    guard var object = decoded as? [String: Any] else { throw Failure.invalidRoot }

    if let rawVersion = object["schemaVersion"] {
      guard let number = rawVersion as? NSNumber,
            CFGetTypeID(number) != CFBooleanGetTypeID(),
            number.doubleValue.isFinite,
            number.doubleValue == Double(number.intValue) else {
        throw Failure.invalidVersion
      }
      if number.intValue == PDFMagicConfigurationSchema.currentVersion {
        _ = try PDFMagicConfigurationSchema.decoded(from: data)
        return data
      }
      guard number.intValue == 0 else { throw Failure.invalidVersion }
    }

    for key in ["showScanProgress", "showSuccessfulScanNotifications", "showBlockedFileNotifications"] {
      if let value = object[key], !(value is NSNull) {
        guard let number = value as? NSNumber,
              CFGetTypeID(number) == CFBooleanGetTypeID() else {
          throw Failure.invalidLegacyValue(key)
        }
      }
    }

    object["schemaVersion"] = PDFMagicConfigurationSchema.currentVersion
    let upgraded = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    _ = try PDFMagicConfigurationSchema.decoded(from: upgraded)
    return upgraded
  }

  // Capture the actual pre-schema UserDefaults settings as a v1 snapshot,
  // preserving explicit false choices and leaving absent keys unspecified.
  // The caller, not this migrator, is responsible for durable persistence.
  static func snapshotLegacyPreferences(defaults: UserDefaults) throws -> Data {
    func savedBool(_ key: String) throws -> Bool? {
      guard let value = defaults.object(forKey: key) else { return nil }
      guard let number = value as? NSNumber,
            CFGetTypeID(number) == CFBooleanGetTypeID() else {
        throw Failure.invalidLegacyValue(key)
      }
      return number.boolValue
    }

    return try PDFMagicConfigurationSchema(
      showScanProgress: savedBool(ScanProgressPreference.key),
      showSuccessfulScanNotifications: savedBool(SuccessfulScanNotificationPreference.key),
      showBlockedFileNotifications: savedBool(BlockedFileNotificationPreference.key)
    ).encoded()
  }
}

// Explicit in-memory fallback; do not modify persisted preferences.
enum MalformedConfigurationRecovery {
  enum RecoveryError: Error, Equatable {
    case unsupportedVersion(Int)
    case oversized
  }
  enum Outcome: Equatable {
    case loaded(PDFMagicConfigurationSchema)
    case recovered(PDFMagicConfigurationSchema)
  }
  private struct VersionProbe: Decodable {
    let schemaVersion: Int?
  }
  static func decode(_ data: Data) throws -> Outcome {
    guard data.count <= 65_536 else { throw RecoveryError.oversized }
    if let probe = try? JSONDecoder().decode(VersionProbe.self, from: data),
       let version = probe.schemaVersion,
       version != PDFMagicConfigurationSchema.currentVersion {
      throw RecoveryError.unsupportedVersion(version)
    }
    if let valid = try? PDFMagicConfigurationSchema.decoded(from: data) {
      return .loaded(valid)
    }
    // Salvage valid presentation choices and default only invalid fields.
    // Preserve the original bytes, including any unknown future fields.
    let fields = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    return .recovered(PDFMagicConfigurationSchema(
      showScanProgress: boolean(fields?["showScanProgress"]),
      showSuccessfulScanNotifications: boolean(fields?["showSuccessfulScanNotifications"]),
      showBlockedFileNotifications: boolean(fields?["showBlockedFileNotifications"])
    ))
  }
  private static func boolean(_ value: Any?) -> Bool? {
    // Do not mistake JSON integers for booleans via NSNumber bridging.
    guard let number = value as? NSNumber,
          CFGetTypeID(number) == CFBooleanGetTypeID() else { return nil }
    return number.boolValue
  }
}
