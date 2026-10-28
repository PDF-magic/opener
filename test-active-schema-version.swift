import Foundation

@main
struct ActiveConfigurationSchemaVersionTests {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.active-schema-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Could not create isolated test defaults")
    }
    defer { defaults.removePersistentDomain(forName: suite) }
    let versionKey = ActiveConfigurationSchemaVersion.key
    let expected = PDFMagicConfigurationSchema.currentVersion

    precondition(defaults.object(forKey: versionKey) == nil)
    precondition(ActiveConfigurationSchemaVersion.read(defaults: defaults) == nil)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.object(forKey: versionKey) as? Int == expected,
                 "first launch must persist the active schema version")

    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    defaults.set(true, forKey: BlockedFileNotificationPreference.key)
    defaults.set("keep", forKey: "unrelatedCustomValue")
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(ActiveConfigurationSchemaVersion.read(defaults: defaults) == expected)
    precondition(defaults.object(forKey: ScanProgressPreference.key) as? Bool == false)
    precondition(defaults.object(forKey: SuccessfulScanNotificationPreference.key) as? Bool == true)
    precondition(defaults.object(forKey: BlockedFileNotificationPreference.key) as? Bool == true)
    precondition(defaults.string(forKey: "unrelatedCustomValue") == "keep")

    // A newer version must be preserved, not overwritten or initialized as v1.
    defaults.set(expected + 1, forKey: versionKey)
    defaults.removeObject(forKey: SuccessfulScanNotificationPreference.key)
    precondition(ActiveConfigurationSchemaVersion.read(defaults: defaults) == expected + 1)
    precondition(!InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.object(forKey: versionKey) as? Int == expected + 1)
    precondition(defaults.object(forKey: SuccessfulScanNotificationPreference.key) == nil)

    // Malformed metadata must not be mistaken for the active version.
    for invalid: Any in ["invalid", true, 0] {
      defaults.set(invalid, forKey: versionKey)
      precondition(ActiveConfigurationSchemaVersion.read(defaults: defaults) == nil)
      precondition(!InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.object(forKey: SuccessfulScanNotificationPreference.key) == nil)
    }

    // Recreate only a missing marker while leaving all other preferences intact.
    defaults.removeObject(forKey: versionKey)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(ActiveConfigurationSchemaVersion.read(defaults: defaults) == expected)
    precondition(defaults.object(forKey: ScanProgressPreference.key) as? Bool == false)
    precondition(defaults.object(forKey: BlockedFileNotificationPreference.key) as? Bool == true)
    precondition(defaults.string(forKey: "unrelatedCustomValue") == "keep")
    precondition(!ActiveConfigurationSchemaVersion.recordIfNeeded(defaults: nil))
    print("Active configuration schema version tests passed")
  }
}
