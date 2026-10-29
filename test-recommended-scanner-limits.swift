import Foundation

// opener-0404: the reset is an explicit, scoped opt-out from optional
// limit-override metadata, never a way to change the installed scan gate.
@main
struct RecommendedScannerLimitsTests {
  static func fresh(_ label: String) -> (String, UserDefaults) {
    let name = "local.studio.pdf-magic-opener.recommended-limits-\(label).\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: name) else {
      fatalError("Cannot create isolated test suite")
    }
    return (name, defaults)
  }

  static func main() {
    let key = RecommendedScannerLimitsReset.concurrencyOverrideKey

    do {
      let (suite, defaults) = fresh("explicit")
      defer { defaults.removePersistentDomain(forName: suite) }
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      defaults.set(1, forKey: key)
      defaults.set(false, forKey: ScanProgressPreference.key)
      defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
      defaults.set("org.mozilla.firefox", forKey: "browserSelection")
      defaults.set("maximum", forKey: PlannedProtectionLevelPreference.key)
      defaults.set("future-custom-setting", forKey: "unknownPreference")
      precondition(defaults.synchronize())

      precondition(RecommendedScannerLimitsReset.restore(defaults: defaults) == .restored)
      guard let reopened = UserDefaults(suiteName: suite) else { fatalError("Reopen failed") }
      precondition(reopened.synchronize())
      precondition(reopened.object(forKey: key) == nil)
      precondition(reopened.object(forKey: ScanProgressPreference.key) as? Bool == false)
      precondition(reopened.object(forKey: SuccessfulScanNotificationPreference.key) as? Bool == true)
      precondition(reopened.string(forKey: "browserSelection") == "org.mozilla.firefox")
      precondition(reopened.string(forKey: PlannedProtectionLevelPreference.key) == "maximum")
      precondition(reopened.string(forKey: "unknownPreference") == "future-custom-setting")
      precondition(SelectedProtectionProfilePreference.selected(defaults: reopened) == .builtIn)
      precondition(RecommendedScannerLimitsReset.restore(defaults: defaults) == .alreadyRecommended)
    }

    do {
      let (suite, defaults) = fresh("empty")
      defer { defaults.removePersistentDomain(forName: suite) }
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(RecommendedScannerLimitsReset.restore(defaults: defaults) == .alreadyRecommended)
      precondition(defaults.object(forKey: key) == nil)
      // Even an out-of-range or malformed *metadata* override may be cleared;
      // the installed gate continues rejecting unsafe runtime settings.
      defaults.set(3, forKey: key)
      precondition(RecommendedScannerLimitsReset.restore(defaults: defaults) == .restored)
      precondition(defaults.object(forKey: key) == nil)
    }

    do {
      let (suite, defaults) = fresh("unsafe-schema")
      defer { defaults.removePersistentDomain(forName: suite) }
      defaults.set(2, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set(1, forKey: key)
      precondition(RecommendedScannerLimitsReset.restore(defaults: defaults) == .unavailable)
      precondition(defaults.object(forKey: key) as? Int == 1)
      defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
      defaults.set("unsupported-future-profile", forKey: SelectedProtectionProfilePreference.key)
      precondition(RecommendedScannerLimitsReset.restore(defaults: defaults) == .unavailable)
      precondition(defaults.object(forKey: key) as? Int == 1)
    }

    precondition(RecommendedScannerLimitsReset.restore(defaults: nil) == .unavailable)
    print("Recommended scanner-limit reset is scoped, persistent and fail-closed")
  }
}
