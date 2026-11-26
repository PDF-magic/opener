import Foundation

func expectMigration(_ condition: @autoclosure () -> Bool, _ message: String) {
  if !condition() { fatalError(message) }
}

@main
struct ConfigurationMigrationTests {
  static func main() throws {
    // Upgrading legacy JSON must preserve both explicit choices and additive fields.
    let legacy = Data(#"{"schemaVersion":0,"showScanProgress":false,"showSuccessfulScanNotifications":true,"showBlockedFileNotifications":false,"customViewer":{"name":"My PDF App"}}"#.utf8)
    let migrated = try PDFMagicConfigurationMigration.migrate(legacy)
    let upgraded = try PDFMagicConfigurationSchema.decoded(from: migrated)
    expectMigration(upgraded.schemaVersion == 1, "legacy payload must upgrade")
    expectMigration(upgraded.showScanProgress == false, "false progress override lost")
    expectMigration(upgraded.showSuccessfulScanNotifications == true, "true success override lost")
    expectMigration(upgraded.showBlockedFileNotifications == false, "false blocked-alert override lost")
    let extra = try JSONSerialization.jsonObject(with: migrated) as! [String: Any]
    expectMigration((extra["customViewer"] as? [String: String])?["name"] == "My PDF App",
                    "unknown custom setting lost")
    let migratedAgain = try PDFMagicConfigurationMigration.migrate(migrated)
    expectMigration(migratedAgain == migrated, "repeated migration must be idempotent")

    let unversioned = Data(#"{"showScanProgress":false,"unrelated":"keep"}"#.utf8)
    let unversionedResult = try PDFMagicConfigurationMigration.migrate(unversioned)
    let unversionedSchema = try PDFMagicConfigurationSchema.decoded(from: unversionedResult)
    expectMigration(unversionedSchema.showScanProgress == false, "unversioned override lost")
    expectMigration(unversionedSchema.showSuccessfulScanNotifications == nil,
                    "absent preferences must remain absent")
    let unversionedObject = try JSONSerialization.jsonObject(with: unversionedResult) as! [String: Any]
    expectMigration(unversionedObject["unrelated"] as? String == "keep", "unrelated key lost")

    // Preserve even whitespace in already-current documents.
    let current = Data(#"{ "schemaVersion": 1, "showScanProgress": false, "extra": [1, 2] }"#.utf8)
    let currentAgain = try PDFMagicConfigurationMigration.migrate(current)
    expectMigration(currentAgain == current, "current version must remain byte-for-byte unchanged")

    for bad in [
      #"[]"#, #"{"schemaVersion":2}"#, #"{"schemaVersion":-1}"#,
      #"{"schemaVersion":0.5}"#, #"{"schemaVersion":true}"#,
      #"{"schemaVersion":"0"}"#, #"{"schemaVersion":null}"#,
      #"{"schemaVersion":0,"showScanProgress":"false"}"#,
      #"{"schemaVersion":0,"showSuccessfulScanNotifications":1}"#,
      #"{"schemaVersion":1,"showBlockedFileNotifications":"true"}"#,
      #"{"schemaVersion":0,"showScanProgress":false"#
    ] {
      do {
        _ = try PDFMagicConfigurationMigration.migrate(Data(bad.utf8))
        fatalError("invalid or future-version configuration accepted: \(bad)")
      } catch {
        // Validation must fail instead of guessing a replacement value.
      }
    }

    // Use an isolated UserDefaults domain; never touch the real preferences.
    let suite = "local.studio.pdf-magic-opener.migration-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else { fatalError("test suite unavailable") }
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    defaults.set("custom", forKey: "unrelatedPreference")
    let before = defaults.dictionaryRepresentation()
    let snapshot = try PDFMagicConfigurationMigration.snapshotLegacyPreferences(defaults: defaults)
    let schema = try PDFMagicConfigurationSchema.decoded(from: snapshot)
    expectMigration(schema.showScanProgress == false, "legacy false UserDefaults lost")
    expectMigration(schema.showSuccessfulScanNotifications == true, "legacy true UserDefaults lost")
    expectMigration(schema.showBlockedFileNotifications == nil, "absent legacy key materialized")
    expectMigration(NSDictionary(dictionary: before).isEqual(to: defaults.dictionaryRepresentation()),
                    "migration must not write to UserDefaults")

    defaults.set("false", forKey: BlockedFileNotificationPreference.key)
    do {
      _ = try PDFMagicConfigurationMigration.snapshotLegacyPreferences(defaults: defaults)
      fatalError("invalid legacy preference was silently converted")
    } catch {
      expectMigration(defaults.string(forKey: BlockedFileNotificationPreference.key) == "false",
                      "invalid value must remain unchanged")
    }
    print("Configuration schema migration tests passed")
  }
}
