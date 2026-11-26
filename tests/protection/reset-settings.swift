import Foundation

// opener-0340: never reset scanner policy, browser or other preferences.
@main
struct TestProtectionSettingsReset {
  static func fresh(_ context: String) -> (String, UserDefaults) {
    let name = "local.studio.pdf-magic-opener.reset-protection-\(context).\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: name) else {
      fatalError("No isolated defaults suite")
    }
    return (name, defaults)
  }

  static func main() {
    let key = PlannedProtectionLevelPreference.key
    let active = SelectedProtectionProfilePreference.key

    // A legacy Standard user chooses another preview; confirming reset
    // returns only the preview to Standard across a process-style reopen.
    do {
      let (suite, defaults) = fresh("legacy")
      defer { defaults.removePersistentDomain(forName: suite) }
      defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set("built-in", forKey: active)
      defaults.set(false, forKey: ScanProgressPreference.key)
      defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
      defaults.set("org.mozilla.firefox", forKey: "browserSelection")
      defaults.set("future-customization", forKey: "unrelated")
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == "standard")
      for choice in [PreferredProtectionLevel.enhanced, .maximum] {
        precondition(PlannedProtectionLevelPreference.saveExplicitChoice(choice, defaults: defaults))
        precondition(ProtectionSettingsReset.reset(defaults: defaults))
        precondition(defaults.string(forKey: key) == "standard")
        precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == .standard)
        guard let reopened = UserDefaults(suiteName: suite) else { fatalError("Reopen failed") }
        precondition(reopened.synchronize())
        precondition(reopened.string(forKey: key) == "standard")
        precondition(reopened.string(forKey: active) == "built-in")
        precondition(reopened.string(forKey: "browserSelection") == "org.mozilla.firefox")
        precondition(reopened.string(forKey: "unrelated") == "future-customization")
        precondition(reopened.object(forKey: ScanProgressPreference.key) as? Bool == false)
        precondition(reopened.object(forKey: SuccessfulScanNotificationPreference.key) as? Bool == true)
      }
      precondition(ProtectionSettingsReset.reset(defaults: defaults)) // Idempotent.
      precondition(defaults.string(forKey: key) == "standard")
    }

    // A new installation's neutral marker cannot accidentally trigger a
    // scanner-policy switch; an explicit confirmed reset selects only the
    // Standard planned preview and survives reinitialization.
    do {
      let (suite, defaults) = fresh("new")
      defer { defaults.removePersistentDomain(forName: suite) }
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == "unassigned")
      precondition(ProtectionSettingsReset.reset(defaults: defaults))
      precondition(defaults.string(forKey: key) == "standard")
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == "standard")
      precondition(defaults.string(forKey: active) == "built-in")
    }

    // Never silently replace an unknown/future or malformed saved tier.
    for bad in ["future-level", "", "unsupported"] {
      let (suite, defaults) = fresh("unknown")
      defer { defaults.removePersistentDomain(forName: suite) }
      defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set("built-in", forKey: active)
      defaults.set(bad, forKey: key)
      precondition(!ProtectionSettingsReset.reset(defaults: defaults))
      precondition(defaults.string(forKey: key) == bad)
    }

    // Malformed values, absent keys, unsupported active policy, future
    // schema and unavailable persistence must fail closed without repairs.
    do {
      let (suite, defaults) = fresh("refusals")
      defer { defaults.removePersistentDomain(forName: suite) }
      precondition(!ProtectionSettingsReset.reset(defaults: defaults))
      defaults.set(2, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set("enhanced", forKey: key)
      precondition(!ProtectionSettingsReset.reset(defaults: defaults))
      precondition(defaults.string(forKey: key) == "enhanced")
      defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set("future-scanner", forKey: active)
      precondition(!ProtectionSettingsReset.reset(defaults: defaults))
      precondition(defaults.string(forKey: active) == "future-scanner")
      defaults.set("built-in", forKey: active)
      defaults.set(true, forKey: key)
      precondition(!ProtectionSettingsReset.reset(defaults: defaults))
      precondition(defaults.object(forKey: key) as? Bool == true)
    }
    precondition(!ProtectionSettingsReset.reset(defaults: nil))
    print("Protection reset is scoped, persisted, confirmed and fail-closed")
  }
}
