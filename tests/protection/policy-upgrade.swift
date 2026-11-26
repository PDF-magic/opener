import Foundation

@main
struct PolicySettingsUpgradeTests {
  static func main() throws {
    // Upgrading pre-policy schema 1 adds only an absent Built-in profile.
    let legacy = Data(#"{"schemaVersion":1,"showScanProgress":false,"showSuccessfulScanNotifications":true,"showBlockedFileNotifications":false,"customBrowser":"com.example.viewer","futurePolicy":{"choice":"keep"}}"#.utf8)
    let upgraded = try PDFMagicPolicySettingsUpgrade.upgradeDocument(legacy)
    let decoded = try PDFMagicConfigurationSchema.decoded(from: upgraded)
    precondition(decoded.selectedProtectionProfile == .builtIn)
    precondition(decoded.showScanProgress == false)
    precondition(decoded.showSuccessfulScanNotifications == true)
    precondition(decoded.showBlockedFileNotifications == false)
    let original = try JSONSerialization.jsonObject(with: legacy) as! [String: Any]
    let after = try JSONSerialization.jsonObject(with: upgraded) as! [String: Any]
    let preserved = after.filter { $0.key != "selectedProtectionProfile" }
    precondition(NSDictionary(dictionary: original).isEqual(to: preserved),
                 "Upgrade changed an existing preference or custom field")
    precondition(after["selectedProtectionProfile"] as? String == "built-in")
    let repeated = try PDFMagicPolicySettingsUpgrade.upgradeDocument(upgraded)
    precondition(repeated == upgraded, "Repeating upgrade must preserve bytes")

    // Already-configured Built-in selections must remain byte-for-byte intact.
    let explicit = Data(#"{ "schemaVersion": 1, "selectedProtectionProfile":"built-in", "custom":"unchanged" }"#.utf8)
    let explicitAgain = try PDFMagicPolicySettingsUpgrade.upgradeDocument(explicit)
    precondition(explicitAgain == explicit)

    // The existing version-zero/unversioned migration is a prerequisite, not a
    // second policy schema: preserve explicit bools and unrelated settings.
    for raw in [
      #"{"schemaVersion":0,"showScanProgress":false,"custom":"keep"}"#,
      #"{"showScanProgress":false,"custom":"keep"}"#,
    ] {
      let migrated = try PDFMagicPolicySettingsUpgrade.upgradeDocument(Data(raw.utf8))
      let model = try PDFMagicConfigurationSchema.decoded(from: migrated)
      precondition(model.schemaVersion == PDFMagicConfigurationSchema.currentVersion)
      precondition(model.showScanProgress == false)
      precondition(model.selectedProtectionProfile == .builtIn)
      let obj = try JSONSerialization.jsonObject(with: migrated) as! [String: Any]
      precondition(obj["custom"] as? String == "keep")
    }

    // No unknown, invalid, future, malformed or explicitly null policy may
    // be coerced into a supported profile during an upgrade.
    for raw in [
      #"{"schemaVersion":1,"selectedProtectionProfile":"enhanced"}"#,
      #"{"schemaVersion":1,"selectedProtectionProfile":"unknown"}"#,
      #"{"schemaVersion":1,"selectedProtectionProfile":true}"#,
      #"{"schemaVersion":1,"selectedProtectionProfile":null}"#,
      #"{"schemaVersion":0,"selectedProtectionProfile":"maximum"}"#,
      #"{"schemaVersion":2,"selectedProtectionProfile":"built-in"}"#,
      #"{"schemaVersion":1,"showScanProgress":"no"}"#,
      #"{"schemaVersion":0,"showScanProgress":123}"#,
      #"{"schemaVersion":1,"custom": "#,
    ] {
      do {
        _ = try PDFMagicPolicySettingsUpgrade.upgradeDocument(Data(raw.utf8))
        fatalError("Invalid or unsupported source was upgraded: \(raw)")
      } catch {}
    }

    let suite = "local.studio.pdf-magic-opener.upgrade-policy.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else { fatalError("isolated suite") }
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    defaults.set("custom-browser", forKey: "customChoice")
    precondition(PDFMagicPolicySettingsUpgrade.seedMissingStoredPolicy(defaults: defaults))
    precondition(defaults.string(forKey: SelectedProtectionProfilePreference.key) == "built-in")
    precondition(!PDFMagicPolicySettingsUpgrade.seedMissingStoredPolicy(defaults: defaults))
    precondition(defaults.object(forKey: ScanProgressPreference.key) as? Bool == false)
    precondition(defaults.object(forKey: SuccessfulScanNotificationPreference.key) as? Bool == true)
    precondition(defaults.string(forKey: "customChoice") == "custom-browser")

    // Reinstall/restart does not rewrite existing customization or a future
    // policy identifier. InitialConfiguration calls this exact upgrade path.
    defaults.set("planned-future-profile", forKey: SelectedProtectionProfilePreference.key)
    precondition(!PDFMagicPolicySettingsUpgrade.seedMissingStoredPolicy(defaults: defaults))
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.string(forKey: SelectedProtectionProfilePreference.key)
                 == "planned-future-profile")
    precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == nil)
    defaults.removeObject(forKey: SelectedProtectionProfilePreference.key)

    defaults.set(2, forKey: ActiveConfigurationSchemaVersion.key)
    precondition(!PDFMagicPolicySettingsUpgrade.seedMissingStoredPolicy(defaults: defaults))
    precondition(!InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.object(forKey: SelectedProtectionProfilePreference.key) == nil)
    defaults.set("invalid", forKey: ActiveConfigurationSchemaVersion.key)
    precondition(!PDFMagicPolicySettingsUpgrade.seedMissingStoredPolicy(defaults: defaults))
    precondition(defaults.object(forKey: SelectedProtectionProfilePreference.key) == nil)

    // First run on an existing compatible v1 domain performs the upgrade.
    defaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.string(forKey: SelectedProtectionProfilePreference.key) == "built-in")
    precondition(defaults.string(forKey: "customChoice") == "custom-browser")
    precondition(defaults.object(forKey: ScanProgressPreference.key) as? Bool == false)
    print("Policy settings upgrade tests passed")
  }
}
