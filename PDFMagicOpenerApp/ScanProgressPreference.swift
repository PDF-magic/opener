import Foundation
import CoreFoundation

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


// Presentation-only duplicate suppression. This never persists scan paths,
// alters user preferences, or controls blocking/scan decisions. The 30-second
// window only suppresses repeats of the same document AND outcome.
enum ScanNotificationDeduplication {
  static let repeatWindow: TimeInterval = 30

  static func shouldQueue(
    identifier: String,
    delivered: [(identifier: String, date: Date)],
    pendingIdentifiers: [String],
    now: Date
  ) -> Bool {
    if pendingIdentifiers.contains(identifier) { return false }
    return !delivered.contains { notice in
      guard notice.identifier == identifier else { return false }
      let age = now.timeIntervalSince(notice.date)
      return age >= 0 && age < repeatWindow
    }
  }
}

// Reserve before asynchronous permission/delivery callbacks to prevent
// simultaneous attempts in one helper process. No disk writes or path storage.
final class ScanNotificationReservation {
  private let lock = NSLock()
  private var recent: [String: Date] = [:]

  func reserve(_ identifier: String, now: Date = Date()) -> Bool {
    lock.lock()
    defer { lock.unlock() }
    recent = recent.filter { _, timestamp in
      let age = now.timeIntervalSince(timestamp)
      return age >= 0 && age < ScanNotificationDeduplication.repeatWindow
    }
    guard recent[identifier] == nil else { return false }
    recent[identifier] = now
    return true
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

// The scanner emits the fixed, path-free diagnostic below only for a validated
// non-heuristic ClamAV malware verdict. The native handler invokes this scanner
// with exactly one file per child process, so the request index is always 1.
// Never infer malware from a substring, arbitrary stderr, or a failed exit alone.
enum BlockedFileNotificationKind: Equatable {
  case none
  case blocked
  case malwareDetected
}

// Optional blocked-open alert delivery; scanner verdicts and warnings never depend on it.
enum BlockedFileNotificationPreference {
  private static let confirmedMalwareFailure =
    "Scan request 1: Malware was detected; opening was stopped.\n"
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

  static func notificationKind(
    failure: String?, cancelled: Bool, enabled: Bool = isEnabled()
  ) -> BlockedFileNotificationKind {
    guard shouldNotify(failure: failure, cancelled: cancelled, enabled: enabled) else {
      return .none
    }
    return failure == confirmedMalwareFailure ? .malwareDetected : .blocked
  }
}

// Only exact, path-free diagnostics emitted by the installed one-file scan gate
// can identify an operational scan failure. This is presentation-only: the
// existing opt-in and mandatory failure alert remain authoritative.
enum FailedScanNotificationClassification {
  private static let verifiedFailures: Set<String> = [
    "Scan request 1: The malware scan could not finish; opening was stopped.\n",
    "Scan request 1: The malware scan did not confirm a complete scan; opening was stopped.\n",
    "Scan request 1: The malware scan timed out; opening was stopped.\n",
    "Scan request 1: ClamAV is unavailable. Run the Allow and Open installer again.\n",
    "Scan request 1: Malware signatures are unavailable. Run update-malware-signatures.sh.\n",
    "Scan request 1: Malware signatures have not been checked in 48 hours. Run update-malware-signatures.sh.\n",
    "Scan request 1: The malware signature database is incomplete. Run update-malware-signatures.sh.\n",
    "Scan request 1: ClamAV scanner version could not be verified. Reinstall ClamAV before opening files.\n",
    "Scan request 1: Unsupported ClamAV scanner version. Install ClamAV 1.4 or 1.5 before opening files.\n",
    "The malware scan exceeded its execution timeout; opening was stopped.",
    "The malware scan could not finish.",
    "The installed scan helper is missing. Reinstall PDF Magic Opener.",
    "The scan helper could not start. Reinstall PDF Magic Opener.",
  ]

  static func shouldShowFailedScanNotice(
    failure: String?,
    cancelled: Bool,
    enabled: Bool = BlockedFileNotificationPreference.isEnabled()
  ) -> Bool {
    guard BlockedFileNotificationPreference.shouldNotify(
      failure: failure, cancelled: cancelled, enabled: enabled
    ), let failure else { return false }
    return verifiedFailures.contains(failure)
  }
}

// Optional browser-download *scope* preference only. It cannot grant browser
// permissions, enable monitoring, authorize an open, or alter the mandatory
// installed ClamAV scanner. Native Finder/file scans are never filtered here.
// The browser download coordinator currently supports PDF candidates only;
// this opt-in is saved for a future independently verified non-PDF integration.
enum ScanOtherSupportedFilesPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "scanOtherSupportedFiles"

  static func isEnabled(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    _ = defaults?.synchronize()
    // Malformed, missing or non-Boolean values do not constitute consent.
    guard let defaults, let raw = defaults.object(forKey: key) as? NSNumber,
          CFGetTypeID(raw) == CFBooleanGetTypeID() else { return false }
    return raw.boolValue
  }

  @discardableResult
  static func save(
    _ enabled: Bool,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    let previous = defaults.object(forKey: key)
    func restorePrevious() {
      if let previous { defaults.set(previous, forKey: key) }
      else { defaults.removeObject(forKey: key) }
      _ = defaults.synchronize()
    }

    // UserDefaults can compare numeric 1/0 and Boolean true/false as equal,
    // leaving an existing malformed integer on disk after set(Bool).
    // Only an explicit save may normalize this key; flush its removal first.
    let previousWasBoolean = (previous as? NSNumber).map {
      CFGetTypeID($0) == CFBooleanGetTypeID()
    } ?? false
    if previous != nil && !previousWasBoolean {
      defaults.removeObject(forKey: key)
      guard defaults.synchronize() else {
        restorePrevious()
        return false
      }
    }
    defaults.set(enabled, forKey: key)
    if defaults.synchronize(), isEnabled(defaults: defaults) == enabled {
      return true
    }
    // Never discard an earlier explicit choice on a failed save.
    restorePrevious()
    return false
  }
}

// The installed scanner currently has only one mandatory policy. Persist its
// identifier separately from scanner controls; unsupported future identifiers
// remain intact and are not silently treated as the Built-in selection.
enum ProtectionProfileIdentifier: String, Codable {
  case builtIn = "built-in"
}

enum SelectedProtectionProfilePreference {
  static let key = "selectedProtectionProfile"
  static let suiteName = ScanProgressPreference.suiteName
  static let initialProfile: ProtectionProfileIdentifier = .builtIn

  static func selected(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> ProtectionProfileIdentifier? {
    guard let defaults else { return nil }
    _ = defaults.synchronize()
    guard let value = defaults.object(forKey: key) else { return initialProfile }
    guard let raw = value as? String else { return nil }
    return ProtectionProfileIdentifier(rawValue: raw)
  }

  @discardableResult
  static func save(
    _ profile: ProtectionProfileIdentifier,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    let original = defaults.object(forKey: key)
    defaults.set(profile.rawValue, forKey: key)
    if defaults.synchronize() && selected(defaults: defaults) == profile {
      return true
    }
    // Do not discard a pre-existing preference if persistence fails.
    if let original { defaults.set(original, forKey: key) }
    else { defaults.removeObject(forKey: key) }
    _ = defaults.synchronize()
    return false
  }
}

// This is a *planned level preference*, never the installed scanner policy.
// Existing installations get the Standard preview preference; new installs
// retain no named preference until a separately verified selection workflow.
// Neither this marker nor an explicit user change authorizes opening a PDF.
enum PreferredProtectionLevel: String {
  case standard
  case enhanced
  case maximum
}

enum PlannedProtectionLevelPreference {
  static let key = "preferredProtectionLevel"
  // Distinguish a fresh installation from an older one across later launches.
  // This value is not a selectable protection tier or active scanner policy.
  static let newInstallationMarker = "unassigned"
  static let suiteName = ScanProgressPreference.suiteName

  static func selected(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> PreferredProtectionLevel? {
    guard let defaults else { return nil }
    _ = defaults.synchronize()
    guard let raw = defaults.object(forKey: key) as? String else { return nil }
    return PreferredProtectionLevel(rawValue: raw)
  }

  // Determine the cohort *before* InitialConfiguration creates any defaults.
  // Ignore unrelated arbitrary application keys; require a recognized legacy
  // configuration marker or an existing supported preference.
  static func wasInstalledBeforeInitialization(defaults: UserDefaults) -> Bool {
    let legacyKeys = [
      ActiveConfigurationSchemaVersion.key,
      SelectedProtectionProfilePreference.key,
      ScanProgressPreference.key,
      SuccessfulScanNotificationPreference.key,
      BlockedFileNotificationPreference.key,
    ]
    return legacyKeys.contains { defaults.object(forKey: $0) != nil }
  }

  // Existing installations keep Standard, while a new installation receives
  // a neutral marker that prevents false legacy detection after app restart.
  // Both cases require a valid schema and Built-in effective scanner policy.
  // Never reset an explicit user selection or malformed/future value.
  @discardableResult
  static func initializeForInstallation(
    defaults: UserDefaults, existingBeforeInitialization: Bool
  ) -> Bool {
    guard ActiveConfigurationSchemaVersion.read(defaults: defaults) ==
            PDFMagicConfigurationSchema.currentVersion,
          SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn,
          defaults.object(forKey: key) == nil else { return false }
    // A fresh install needs a durable neutral marker; otherwise a second
    // launch would misidentify its newly written baseline keys as legacy.
    defaults.set(existingBeforeInitialization
      ? PreferredProtectionLevel.standard.rawValue : newInstallationMarker,
      forKey: key)
    return true
  }

  // An explicit preview choice is separate from selectedProtectionProfile.
  // It never changes the effective Built-in policy or scanner settings.
  @discardableResult
  static func saveExplicitChoice(
    _ level: PreferredProtectionLevel,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults,
          ActiveConfigurationSchemaVersion.read(defaults: defaults) ==
            PDFMagicConfigurationSchema.currentVersion,
          SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn else {
      return false
    }
    let oldValue = defaults.object(forKey: key)
    defaults.set(level.rawValue, forKey: key)
    if defaults.synchronize() && selected(defaults: defaults) == level { return true }
    if let oldValue { defaults.set(oldValue, forKey: key) }
    else { defaults.removeObject(forKey: key) }
    _ = defaults.synchronize()
    return false
  }
}

// Explicit, narrow reset of the *planned preview* metadata only. The
// effective Built-in scan policy and all other preferences are out of scope.
// Unknown future selections are never coerced into a known profile.
enum ProtectionSettingsReset {
  @discardableResult
  static func reset(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    guard ActiveConfigurationSchemaVersion.read(defaults: defaults) ==
            PDFMagicConfigurationSchema.currentVersion,
          SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn,
          let original = defaults.object(forKey: PlannedProtectionLevelPreference.key) as? String,
          original == PlannedProtectionLevelPreference.newInstallationMarker ||
            PreferredProtectionLevel(rawValue: original) != nil else {
      return false
    }

    // Standard is the safe existing-installation planned-level baseline;
    // this does not authorize the unimplemented Standard scanner policy.
    let standard = PreferredProtectionLevel.standard.rawValue
    if original == standard { return true }
    defaults.set(standard, forKey: PlannedProtectionLevelPreference.key)
    if defaults.synchronize(),
       defaults.string(forKey: PlannedProtectionLevelPreference.key) == standard,
       SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn {
      return true
    }

    // Persistence errors must not silently discard an explicit choice.
    defaults.set(original, forKey: PlannedProtectionLevelPreference.key)
    _ = defaults.synchronize()
    return false
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
    // Capture legacy state before a first-run initialization writes its keys.
    let existingBeforeInitialization =
      PlannedProtectionLevelPreference.wasInstalledBeforeInitialization(defaults: defaults)
    // Record the active version without overwriting incompatible metadata.
    guard ActiveConfigurationSchemaVersion.recordIfNeeded(defaults: defaults) else { return false }
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
    if PDFMagicPolicySettingsUpgrade.seedMissingStoredPolicy(defaults: defaults) {
      initializedMissingSetting = true
    }
    if PlannedProtectionLevelPreference.initializeForInstallation(
      defaults: defaults, existingBeforeInitialization: existingBeforeInitialization
    ) {
      initializedMissingSetting = true
    }
    // A relaunch or an in-place upgrade must not re-save already persisted
    // preferences. Only the first creation of missing keys needs a flush.
    return !initializedMissingSetting || defaults.synchronize()
  }
}

// Record the schema version in the same shared defaults suite as the active
// preferences. This metadata does not migrate or reset any user setting.
enum ActiveConfigurationSchemaVersion {
  static let key = "schemaVersion"

  static func read(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Int? {
    guard let defaults,
          let raw = defaults.object(forKey: key),
          let numeric = raw as? NSNumber,
          CFGetTypeID(numeric) != CFBooleanGetTypeID(),
          let version = raw as? Int, version > 0 else { return nil }
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

// Additive upgrade for policy settings introduced after legacy presentation
// configuration. No schema-version bump is necessary: the only supported
// identifier is the existing Built-in scan policy, and older readers ignore
// this optional field. This path never activates a planned protection tier.
enum PDFMagicPolicySettingsUpgrade {
  enum Failure: Error {
    case invalidPolicyValue
  }

  // Upgrade v0, unversioned or current v1 JSON snapshots without discarding
  // unrelated or future keys. Only an ABSENT field is supplied a safe value;
  // explicit malformed/unsupported selections must not be silently repaired.
  static func upgradeDocument(_ data: Data) throws -> Data {
    let normalized = try PDFMagicConfigurationMigration.migrate(data)
    guard var object = try JSONSerialization.jsonObject(with: normalized) as? [String: Any]
    else { throw PDFMagicConfigurationMigration.Failure.invalidRoot }
    let key = SelectedProtectionProfilePreference.key
    if let saved = object[key] {
      guard let raw = saved as? String,
            ProtectionProfileIdentifier(rawValue: raw) != nil else {
        throw Failure.invalidPolicyValue
      }
      // Preserve current payload bytes, including custom layout and unknowns.
      return normalized
    }
    object[key] = SelectedProtectionProfilePreference.initialProfile.rawValue
    let upgraded = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    _ = try PDFMagicConfigurationSchema.decoded(from: upgraded)
    return upgraded
  }

  // Use the same additive policy-upgrade rule on actual legacy UserDefaults.
  // InitialConfiguration owns the final persistence/synchronize operation.
  // Future or malformed schema markers cannot trigger any mutation.
  @discardableResult
  static func seedMissingStoredPolicy(defaults: UserDefaults) -> Bool {
    guard ActiveConfigurationSchemaVersion.read(defaults: defaults) ==
            PDFMagicConfigurationSchema.currentVersion,
          defaults.object(forKey: SelectedProtectionProfilePreference.key) == nil else {
      return false
    }
    defaults.set(SelectedProtectionProfilePreference.initialProfile.rawValue,
                 forKey: SelectedProtectionProfilePreference.key)
    return true
  }
}


// Optional browser-download notification *preference* only. The installed
// opener retains independent blocking and safety messages even when disabled.
// No browser or native delivery integration currently consumes this setting.
enum DownloadScanNotificationOutcome {
  case failed
  case incomplete
  case clean
  case blocked
  case cancelled
  case unknown
}

enum DownloadFailedScanNotificationPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "notifyOnFailedScan"

  // Explicit opt-in. Missing, malformed or unavailable settings are disabled.
  static func isEnabled(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    guard let raw = defaults.object(forKey: key) as? NSNumber,
          CFGetTypeID(raw) == CFBooleanGetTypeID() else { return false }
    return raw.boolValue
  }

  @discardableResult
  static func save(
    _ enabled: Bool,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    let previous = defaults.object(forKey: key)
    func restore() {
      if let previous { defaults.set(previous, forKey: key) }
      else { defaults.removeObject(forKey: key) }
      _ = defaults.synchronize()
    }
    // Remove a malformed numeric/string entry first: UserDefaults can
    // otherwise preserve a numeric 1/0 when setting a Boolean equivalent.
    if let previous {
      let valid = (previous as? NSNumber).map {
        CFGetTypeID($0) == CFBooleanGetTypeID()
      } ?? false
      if !valid {
        defaults.removeObject(forKey: key)
        guard defaults.synchronize() else {
          restore()
          return false
        }
      }
    }
    defaults.set(enabled, forKey: key)
    if defaults.synchronize(), isEnabled(defaults: defaults) == enabled {
      return true
    }
    restore()
    return false
  }

  // Must only be called with a result independently classified by an
  // authenticated native coordinator. Download metadata is not scan evidence.
  // This controls optional extra notifications, never required warning UI.
  static func shouldNotify(
    _ outcome: DownloadScanNotificationOutcome,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    switch outcome {
    case .failed, .incomplete:
      return isEnabled(defaults: defaults)
    case .clean, .blocked, .cancelled, .unknown:
      return false
    }
  }
}

// This app has no authenticated live browser-to-native connection observer yet.
// A transport-only host handshake never proves that scanning is available.
// The read-only indicator must not treat saved opt-in or installed apps as health.
enum BrowserNativeConnectionHealth: Equatable {
  case notConnected
  case transportOnly

  // No live observer is installed. Change this only when a separately reviewed
  // authenticated coordinator supplies a current, session-bound status.
  static var current: BrowserNativeConnectionHealth { .notConnected }

  // Future integration boundary: input must come from independently verified
  // host registration, exact extension identity and an authenticated session.
  // The existing v1 handshake explicitly advertises scanAvailable = false.
  // Unrecognized or privileged claims remain unverified.
  static func fromVerifiedHandshake(
    authenticatedSession: Bool,
    protocolVersion: Int,
    hostStatus: String,
    scanAvailable: Bool
  ) -> BrowserNativeConnectionHealth {
    guard authenticatedSession, protocolVersion == 1,
          hostStatus == "transport-only", !scanAvailable else {
      return .notConnected
    }
    return .transportOnly
  }

  var statusLabel: String {
    switch self {
    case .notConnected: return "Not connected"
    case .transportOnly: return "Host reachable — scanning unavailable"
    }
  }

  var detail: String {
    switch self {
    case .notConnected:
      return "No authenticated browser-to-native connection is active. Browser download scanning is not available."
    case .transportOnly:
      return "Native messaging transport is verified, but the scanner is not connected to browser downloads."
    }
  }

  // Mandatory native scanner enforcement is never controlled by this display.
  var scannerConnectionHealthy: Bool { false }
}

// Download scan-result presentation only. No native scanner, browser permission,
// mandatory warning, blocked-file alert, or PDF destination depends
// on this preference. Unverified/incomplete results must remain visible.
enum DownloadWarningDisplayKind {
  case verifiedCleanSummary
  case verifiedInformationalSummary
  case securityWarning
  case scanIncompleteOrFailed
  case unknown
}

enum DownloadWarningOnlyPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "showOnlyWarnings"

  // Preserve existing summary visibility for users who have not opted in.
  // Malformed settings cannot silently suppress any result.
  static func isEnabled(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    guard let stored = defaults.object(forKey: key),
          let value = stored as? NSNumber,
          CFGetTypeID(value) == CFBooleanGetTypeID() else { return false }
    return value.boolValue
  }

  @discardableResult
  static func save(
    _ enabled: Bool,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    let previous = defaults.object(forKey: key)
    defaults.set(enabled, forKey: key)
    if defaults.synchronize(), isEnabled(defaults: defaults) == enabled {
      return true
    }
    if let previous { defaults.set(previous, forKey: key) }
    else { defaults.removeObject(forKey: key) }
    _ = defaults.synchronize()
    return false
  }

  // Call ONLY after an authenticated native coordinator classifies the full
  // canonical scan result. Browser MIME, filename and labels are not verdicts.
  // Optional summaries may be hidden, but every potential warning remains.
  static func shouldPresent(
    _ kind: DownloadWarningDisplayKind,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    switch kind {
    case .verifiedCleanSummary, .verifiedInformationalSummary:
      return !isEnabled(defaults: defaults)
    case .securityWarning, .scanIncompleteOrFailed, .unknown:
      return true
    }
  }
}


// Only recognized optional scanner-limit override metadata is in scope.
// The installed scanner never reads this key; it continues enforcing the
// fixed two-slot gate and its other mandatory safety checks. Future editable
// limits must be separately integrated and explicitly added to this allowlist.
enum RecommendedScannerLimitsReset {
  static let concurrencyOverrideKey = "maxConcurrentScans"

  enum Outcome: Equatable {
    case restored
    case alreadyRecommended
    case unavailable
  }

  static func restore(
    defaults: UserDefaults? = UserDefaults(suiteName: ScanProgressPreference.suiteName)
  ) -> Outcome {
    guard let defaults else { return .unavailable }
    _ = defaults.synchronize()
    // An unsupported/future schema or scanner profile must not be rewritten.
    guard ActiveConfigurationSchemaVersion.read(defaults: defaults) ==
            PDFMagicConfigurationSchema.currentVersion,
          SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn else {
      return .unavailable
    }

    // Absent overrides inherit the installed recommended limit. Never create
    // a new persisted setting merely to make the reset appear successful.
    let previous = defaults.object(forKey: concurrencyOverrideKey)
    guard let previous else { return .alreadyRecommended }
    defaults.removeObject(forKey: concurrencyOverrideKey)
    if defaults.synchronize(),
       defaults.object(forKey: concurrencyOverrideKey) == nil,
       SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn {
      return .restored
    }

    // A failed write must not erase the user's previous explicit choice.
    defaults.set(previous, forKey: concurrencyOverrideKey)
    _ = defaults.synchronize()
    return .unavailable
  }
}

// Opt-in *preference* for a future browser integration, not a runtime grant.
// Do not use this value as a scanner verdict, verified browser permission,
// or authorization to open, scan, or subscribe to downloads.
enum BrowserDownloadMonitoringPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "downloadMonitoringEnabled"

  static func isEnabled(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    // NSNumber bridging can otherwise mistake an integer for a Bool.
    guard let value = defaults.object(forKey: key) as? NSNumber,
          CFGetTypeID(value) == CFBooleanGetTypeID() else { return false }
    return value.boolValue
  }

  @discardableResult
  static func save(
    _ enabled: Bool,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    let original = defaults.object(forKey: key)
    defaults.set(enabled, forKey: key)
    if defaults.synchronize() && isEnabled(defaults: defaults) == enabled {
      return true
    }
    // Roll back only this one key when persistence cannot be confirmed.
    if let original { defaults.set(original, forKey: key) }
    else { defaults.removeObject(forKey: key) }
    _ = defaults.synchronize()
    return false
  }
}


// Future-facing, PER-BROWSER opt-in only. This is not a permission grant or an
// active interception feature. Actual browser/network access and native ClamAV
// scan-before-render must be verified independently before any implementation
// may act on a saved preference. Do not infer eligibility from installation alone.
enum BrowserAutomaticPDFInterceptionPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "automaticPDFInterceptionOptIns"

  // Vendor-documented candidate request/response interception APIs only.
  // Chrome/Edge DNR cannot await a native scan; Firefox's response filter is
  // not wired up. Chromium forks and Safari need per-version verification.
  // Keep this strict list aligned with automatic-interception-capability-matrix.js.
  static let candidateBrowserIDs: Set<String> = [
    "com.google.Chrome", "com.microsoft.edgemac", "org.mozilla.firefox"
  ]

  static func eligibleBrowserIDs(installedIDs: Set<String>) -> Set<String> {
    return installedIDs.intersection(candidateBrowserIDs)
  }

  static func isOptedIn(
    for browserID: String,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard candidateBrowserIDs.contains(browserID), let defaults else { return false }
    _ = defaults.synchronize()
    guard let values = defaults.dictionary(forKey: key),
          let raw = values[browserID] as? NSNumber,
          CFGetTypeID(raw) == CFBooleanGetTypeID() else { return false }
    return raw.boolValue
  }

  @discardableResult
  static func saveOptIn(
    _ optedIn: Bool,
    for browserID: String,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard candidateBrowserIDs.contains(browserID), let defaults else { return false }
    _ = defaults.synchronize()
    let previous = defaults.object(forKey: key)
    // Never silently overwrite malformed or future values for this preference.
    guard previous == nil || previous is [String: Any] else { return false }
    var values = (previous as? [String: Any]) ?? [:]
    values[browserID] = optedIn
    defaults.set(values, forKey: key)
    if defaults.synchronize(),
       isOptedIn(for: browserID, defaults: defaults) == optedIn { return true }
    if let previous { defaults.set(previous, forKey: key) }
    else { defaults.removeObject(forKey: key) }
    _ = defaults.synchronize()
    return false
  }
}

// Browser download scan-result *presentation* only. A missing or malformed
// value preserves visible summaries. This must never change native scanning,
// browser permissions, malware warnings, failures, or the opening decision.
enum DownloadScanResultPresentation {
  case optionalSummary
  case securityWarning
}

enum DownloadScanResultsPreference {
  static let suiteName = ScanProgressPreference.suiteName
  static let key = "showScanResults"

  static func isEnabled(
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return true }
    _ = defaults.synchronize()
    guard let stored = defaults.object(forKey: key) else { return true }
    // An unexpected storage type must not silently suppress results.
    guard let value = stored as? NSNumber,
          CFGetTypeID(value) == CFBooleanGetTypeID() else { return true }
    return value.boolValue
  }

  @discardableResult
  static func save(
    _ enabled: Bool,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    guard let defaults else { return false }
    _ = defaults.synchronize()
    let previous = defaults.object(forKey: key)
    defaults.set(enabled, forKey: key)
    if defaults.synchronize() && isEnabled(defaults: defaults) == enabled {
      return true
    }
    if let previous { defaults.set(previous, forKey: key) }
    else { defaults.removeObject(forKey: key) }
    _ = defaults.synchronize()
    return false
  }

  // Only optional clean/informational summaries are suppressible. A caller
  // MUST independently classify and continue to present security warnings.
  // Neither this function nor the preference produces scanner authorization.
  static func shouldPresent(
    _ category: DownloadScanResultPresentation,
    defaults: UserDefaults? = UserDefaults(suiteName: suiteName)
  ) -> Bool {
    switch category {
    case .optionalSummary: return isEnabled(defaults: defaults)
    case .securityWarning: return true
    }
  }
}

// An explicit, read-only local preflight for a future browser integration.
// Browser installation never proves extension permission, native messaging,
// scanner readiness, or enforcement of browser/OS download opening. Since no
// authenticated live integration exists, this model cannot report success.
struct BrowserIntegrationTestReport: Equatable {
  let detectedCount: Int
  let supportedCount: Int

  var statusLabel: String { "Integration test unavailable" }

  var detail: String {
    "Detected \(detectedCount) of \(supportedCount) supported browsers. " +
    "No authenticated browser-to-native scanner integration is active. " +
    "This check cannot verify downloads, scanner connectivity, or safe opening."
  }
}

enum BrowserIntegrationTest {
  static func run(
    supportedIDs: Set<String>,
    detectedIDs: Set<String>
  ) -> BrowserIntegrationTestReport {
    let supported = supportedIDs.filter { !$0.isEmpty }
    return BrowserIntegrationTestReport(
      detectedCount: supported.filter { detectedIDs.contains($0) }.count,
      supportedCount: supported.count
    )
  }
}

// Read-only presentation of browser download monitoring. Discovery of an
// executable app is not evidence that any extension is authorized, connected,
// listening for downloads, or enforcing the native scanner. No active state
// can be constructed here; only an independently verified future coordinator
// may introduce live monitoring status.
struct BrowserMonitoringStatusRow: Identifiable, Equatable {
  let id: String
  let name: String
  let detected: Bool

  var statusLabel: String { detected ? "Not connected" : "Not detected" }
}

enum BrowserMonitoringStatusDisplay {
  static func rows(
    supported: [(id: String, name: String)],
    detectedIDs: Set<String>
  ) -> [BrowserMonitoringStatusRow] {
    var seen = Set<String>()
    return supported.compactMap { browser in
      guard !browser.id.isEmpty, !browser.name.isEmpty,
            seen.insert(browser.id).inserted else { return nil }
      return BrowserMonitoringStatusRow(
        id: browser.id, name: browser.name,
        detected: detectedIDs.contains(browser.id)
      )
    }
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
  var selectedProtectionProfile: ProtectionProfileIdentifier?

  init(
    showScanProgress: Bool? = nil,
    showSuccessfulScanNotifications: Bool? = nil,
    showBlockedFileNotifications: Bool? = nil,
    selectedProtectionProfile: ProtectionProfileIdentifier? = nil
  ) {
    schemaVersion = Self.currentVersion
    self.showScanProgress = showScanProgress
    self.showSuccessfulScanNotifications = showSuccessfulScanNotifications
    self.showBlockedFileNotifications = showBlockedFileNotifications
    self.selectedProtectionProfile = selectedProtectionProfile
  }

  private enum CodingKeys: String, CodingKey {
    case schemaVersion
    case showScanProgress
    case showSuccessfulScanNotifications
    case showBlockedFileNotifications
    case selectedProtectionProfile
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
    selectedProtectionProfile = try values.decodeIfPresent(
      ProtectionProfileIdentifier.self, forKey: .selectedProtectionProfile
    )
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

    // Only snapshot explicit profile selections: absence stays absent in a
    // legacy snapshot, and an unsupported value cannot be overwritten.
    let profileKey = SelectedProtectionProfilePreference.key
    var selectedProfile: ProtectionProfileIdentifier?
    if let raw = defaults.object(forKey: profileKey) {
      guard let name = raw as? String,
            let profile = ProtectionProfileIdentifier(rawValue: name) else {
        throw Failure.invalidLegacyValue(profileKey)
      }
      selectedProfile = profile
    }
    return try PDFMagicConfigurationSchema(
      showScanProgress: savedBool(ScanProgressPreference.key),
      showSuccessfulScanNotifications: savedBool(SuccessfulScanNotificationPreference.key),
      showBlockedFileNotifications: savedBool(BlockedFileNotificationPreference.key),
      selectedProtectionProfile: selectedProfile
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
      showBlockedFileNotifications: boolean(fields?["showBlockedFileNotifications"]),
      selectedProtectionProfile: (fields?["selectedProtectionProfile"] as? String)
        .flatMap(ProtectionProfileIdentifier.init(rawValue:))
    ))
  }
  private static func boolean(_ value: Any?) -> Bool? {
    // Do not mistake JSON integers for booleans via NSNumber bridging.
    guard let number = value as? NSNumber,
          CFGetTypeID(number) == CFBooleanGetTypeID() else { return nil }
    return number.boolValue
  }
}
