import Foundation

// opener-0334: legacy installations preserve Standard as a planned-level
// preference. The installed scanner remains Built-in and no tier is enabled.
@main
struct TestLegacyStandardPreference {
  static func suite(_ purpose: String) -> (String, UserDefaults) {
    let name = "local.studio.pdf-magic-opener.legacy-standard-\(purpose).\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: name) else {
      fatalError("Could not create isolated defaults")
    }
    return (name, defaults)
  }

  static func main() {
    let key = PlannedProtectionLevelPreference.key
    let selectedPolicy = SelectedProtectionProfilePreference.key

    // A pristine installation must not be mistaken for an upgrade. Its
    // "unassigned" marker survives restart and a second initializer call,
    // leaving future new-install recommendation behavior to a separate task.
    do {
      let (name, defaults) = suite("new")
      defer { defaults.removePersistentDomain(forName: name) }
      precondition(!PlannedProtectionLevelPreference.wasInstalledBeforeInitialization(defaults: defaults))
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == PlannedProtectionLevelPreference.newInstallationMarker)
      precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == nil)
      precondition(defaults.string(forKey: selectedPolicy) == "built-in")
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      guard let reopened = UserDefaults(suiteName: name) else { fatalError("Restart domain unavailable") }
      precondition(reopened.synchronize())
      precondition(InitialConfiguration.createIfNeeded(defaults: reopened))
      precondition(reopened.string(forKey: key) == "unassigned")
      precondition(reopened.string(forKey: selectedPolicy) == "built-in")
    }

    // The previous release wrote a schema-1 marker and Built-in policy.
    // Upgrade must preserve user settings and add only a Standard *preview*
    // preference, not change the enforced profile or scanner.
    do {
      let (name, defaults) = suite("existing")
      defer { defaults.removePersistentDomain(forName: name) }
      defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set("built-in", forKey: selectedPolicy)
      defaults.set(false, forKey: ScanProgressPreference.key)
      defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
      defaults.set("custom.app.viewer", forKey: "browserChoice")
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == "standard")
      precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == .standard)
      precondition(defaults.string(forKey: selectedPolicy) == "built-in")
      precondition(defaults.object(forKey: ScanProgressPreference.key) as? Bool == false)
      precondition(defaults.object(forKey: SuccessfulScanNotificationPreference.key) as? Bool == true)
      precondition(defaults.string(forKey: "browserChoice") == "custom.app.viewer")

      // An explicit user preference wins, including after reinitialization,
      // general reset and opening the settings in another process.
      precondition(PlannedProtectionLevelPreference.saveExplicitChoice(.enhanced, defaults: defaults))
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(GeneralPreferencesReset.reset(defaults: defaults))
      guard let reopened = UserDefaults(suiteName: name) else { fatalError("Restart domain unavailable") }
      precondition(reopened.synchronize())
      precondition(InitialConfiguration.createIfNeeded(defaults: reopened))
      precondition(PlannedProtectionLevelPreference.selected(defaults: reopened) == .enhanced)
      precondition(reopened.string(forKey: key) == "enhanced")
      precondition(reopened.string(forKey: selectedPolicy) == "built-in")
      precondition(reopened.string(forKey: "browserChoice") == "custom.app.viewer")
      precondition(PlannedProtectionLevelPreference.saveExplicitChoice(.maximum, defaults: reopened))
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == "maximum")
      precondition(defaults.string(forKey: selectedPolicy) == "built-in")
    }

    // Pre-schema legacy installs with actual saved preferences still retain
    // Standard; arbitrary unknown keys alone do not prove a legacy install.
    for existing in [true, false] {
      let (name, defaults) = suite(existing ? "unversioned" : "unrelated")
      defer { defaults.removePersistentDomain(forName: name) }
      defaults.set("keep", forKey: "unrelated")
      if existing { defaults.set(false, forKey: ScanProgressPreference.key) }
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == (existing ? "standard" : "unassigned"))
      precondition(defaults.string(forKey: "unrelated") == "keep")
      precondition(defaults.string(forKey: selectedPolicy) == "built-in")
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == (existing ? "standard" : "unassigned"))
    }

    // Never replace an explicit unsupported or future value (even if the
    // selection cannot be interpreted as a valid planned tier).
    for raw in ["future-protection", "", "invalid"] {
      let (name, defaults) = suite("future")
      defer { defaults.removePersistentDomain(forName: name) }
      defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set(raw, forKey: key)
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == raw)
      precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == nil)
    }

    // Incompatible schema and unsupported active policies must not be
    // implicitly repaired into a Standard preference.
    do {
      let (name, defaults) = suite("unsupported")
      defer { defaults.removePersistentDomain(forName: name) }
      defaults.set(2, forKey: ActiveConfigurationSchemaVersion.key)
      precondition(!InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.object(forKey: key) == nil)
      defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set("unrecognized-policy", forKey: selectedPolicy)
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.object(forKey: key) == nil)
      precondition(defaults.string(forKey: selectedPolicy) == "unrecognized-policy")
      precondition(!PlannedProtectionLevelPreference.saveExplicitChoice(.standard, defaults: defaults))
    }

    precondition(!PlannedProtectionLevelPreference.saveExplicitChoice(.standard, defaults: nil))
    precondition(PlannedProtectionLevelPreference.selected(defaults: nil) == nil)
    print("Existing installations preserve Standard, user choices and Built-in scan policy")
  }
}
