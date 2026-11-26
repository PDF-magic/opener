import Foundation

// Regression for repeated app startup after an application replacement.
// Every child process uses a random, disposable UserDefaults suite, never the
// installed application's real shared preferences.
func expectUpgrade(_ condition: @autoclosure () -> Bool, _ message: String) {
  if !condition() { fatalError(message) }
}

@main
struct ApplicationUpgradePreferenceTests {
  static func persistentValues(_ defaults: UserDefaults, suite: String) -> [String: Any] {
    _ = defaults.synchronize()
    return defaults.persistentDomain(forName: suite) ?? [:]
  }

  static func seedNew(_ defaults: UserDefaults) {
    expectUpgrade(InitialConfiguration.createIfNeeded(defaults: defaults),
                  "new installation initialization failed")
    expectUpgrade(defaults.string(forKey: PlannedProtectionLevelPreference.key) ==
                    PlannedProtectionLevelPreference.newInstallationMarker,
                  "new installation must have the neutral planned-level marker")
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    defaults.set(true, forKey: BlockedFileNotificationPreference.key)
    defaults.set(true, forKey: DownloadFailedScanNotificationPreference.key)
    defaults.set(PreferredProtectionLevel.enhanced.rawValue,
                 forKey: PlannedProtectionLevelPreference.key)
    defaults.set(["layout": "compact"], forKey: "unrelatedCustomSetting")
    expectUpgrade(defaults.synchronize(), "failed to persist custom preferences")
  }

  static func verifyNew(_ defaults: UserDefaults, suite: String) {
    expectUpgrade(ActiveConfigurationSchemaVersion.read(defaults: defaults) ==
                    PDFMagicConfigurationSchema.currentVersion, "schema changed")
    expectUpgrade(SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn,
                  "upgrading must not change the effective scan policy")
    expectUpgrade(!ScanProgressPreference.isEnabled(defaults: defaults),
                  "saved disabled progress was reset")
    expectUpgrade(SuccessfulScanNotificationPreference.isEnabled(defaults: defaults),
                  "saved notification opt-in was reset")
    expectUpgrade(defaults.bool(forKey: BlockedFileNotificationPreference.key),
                  "saved blocked alert preference was reset")
    expectUpgrade(DownloadFailedScanNotificationPreference.isEnabled(defaults: defaults),
                  "saved failed-download alert preference was reset")
    expectUpgrade(PlannedProtectionLevelPreference.selected(defaults: defaults) == .enhanced,
                  "saved planned level was reset")
    expectUpgrade((defaults.dictionary(forKey: "unrelatedCustomSetting")?["layout"] as? String)
                    == "compact", "unknown customized setting was lost")
    let before = persistentValues(defaults, suite: suite)
    expectUpgrade(InitialConfiguration.createIfNeeded(defaults: defaults),
                  "upgrade startup failed")
    let after = persistentValues(defaults, suite: suite)
    expectUpgrade(NSDictionary(dictionary: before).isEqual(to: after),
                  "upgrade startup rewrote persisted preferences")
  }

  static func seedLegacy(_ defaults: UserDefaults) {
    // An older app may have saved presentation preferences but no schema or
    // policy metadata. Upgrade should only add missing, safe defaults.
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    defaults.set("existing-browser-override", forKey: "customViewer")
    expectUpgrade(defaults.synchronize(), "failed to seed legacy preferences")
  }

  static func verifyLegacy(_ defaults: UserDefaults, suite: String) {
    expectUpgrade(InitialConfiguration.createIfNeeded(defaults: defaults),
                  "legacy app preferences could not be upgraded")
    expectUpgrade(!ScanProgressPreference.isEnabled(defaults: defaults),
                  "legacy disabled progress was reset")
    expectUpgrade(SuccessfulScanNotificationPreference.isEnabled(defaults: defaults),
                  "legacy notification opt-in was reset")
    expectUpgrade(defaults.string(forKey: "customViewer") == "existing-browser-override",
                  "legacy custom browser override was discarded")
    expectUpgrade(SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn,
                  "legacy migration changed active protection")
    expectUpgrade(PlannedProtectionLevelPreference.selected(defaults: defaults) == .standard,
                  "legacy installation must retain the Standard preview choice")
    let before = persistentValues(defaults, suite: suite)
    expectUpgrade(InitialConfiguration.createIfNeeded(defaults: defaults),
                  "repeat legacy upgrade failed")
    expectUpgrade(NSDictionary(dictionary: before).isEqual(
                    to: persistentValues(defaults, suite: suite)),
                  "repeat legacy upgrade altered stored settings")
  }

  static func seedFuture(_ defaults: UserDefaults) {
    defaults.set(999, forKey: ActiveConfigurationSchemaVersion.key)
    defaults.set("unsupported-future-profile", forKey: SelectedProtectionProfilePreference.key)
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set("do-not-replace", forKey: "unrelatedCustomSetting")
    expectUpgrade(defaults.synchronize(), "failed to seed future-version preferences")
  }

  static func verifyFuture(_ defaults: UserDefaults, suite: String) {
    let before = persistentValues(defaults, suite: suite)
    expectUpgrade(!InitialConfiguration.createIfNeeded(defaults: defaults),
                  "unsupported future schema was silently admitted")
    let after = persistentValues(defaults, suite: suite)
    expectUpgrade(NSDictionary(dictionary: before).isEqual(to: after),
                  "unsupported future schema caused a preference reset")
  }

  static func launch(_ phase: String, suite: String) throws {
    let child = Process()
    child.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
    child.arguments = [phase, suite]
    try child.run()
    child.waitUntilExit()
    expectUpgrade(child.terminationReason == .exit && child.terminationStatus == 0,
                  "separate app launch failed during \(phase)")
  }

  static func main() throws {
    if CommandLine.arguments.count == 3 {
      let phase = CommandLine.arguments[1]
      let suite = CommandLine.arguments[2]
      guard let defaults = UserDefaults(suiteName: suite) else {
        fatalError("could not access isolated upgrade preferences")
      }
      switch phase {
      case "seed-new": seedNew(defaults)
      case "verify-new": verifyNew(defaults, suite: suite)
      case "seed-legacy": seedLegacy(defaults)
      case "verify-legacy": verifyLegacy(defaults, suite: suite)
      case "seed-future": seedFuture(defaults)
      case "verify-future": verifyFuture(defaults, suite: suite)
      default: fatalError("unknown upgrade test phase")
      }
      return
    }
    expectUpgrade(CommandLine.arguments.count == 1, "unexpected test arguments")
    for (seed, verify) in [
      ("seed-new", "verify-new"),
      ("seed-legacy", "verify-legacy"),
      ("seed-future", "verify-future"),
    ] {
      let suite = "local.studio.pdf-magic-opener.upgrade-test.\(UUID().uuidString)"
      guard let defaults = UserDefaults(suiteName: suite) else {
        fatalError("could not create isolated upgrade suite")
      }
      defer {
        defaults.removePersistentDomain(forName: suite)
        _ = defaults.synchronize()
      }
      try launch(seed, suite: suite)
      try launch(verify, suite: suite)
      try launch(verify, suite: suite)
    }
    print("Application upgrade preference preservation passed")
  }
}
