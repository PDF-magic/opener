import Foundation

@main
struct TestSelectedProtectionProfile {
  static func main() throws {
    let suite = "local.studio.pdf-magic-opener.profile-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else { fatalError("Isolated suite unavailable") }
    defer { defaults.removePersistentDomain(forName: suite) }
    let key = SelectedProtectionProfilePreference.key

    // Before first launch, the mandatory Built-in profile is the only known choice.
    precondition(defaults.object(forKey: key) == nil)
    precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.string(forKey: key) == "built-in")
    precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn)
    precondition(ProtectionProfileIdentifier(rawValue: "unsupported") == nil)

    // Save and read from a newly constructed defaults object (app restart).
    defaults.set("custom-browser", forKey: "unrelatedPreference")
    defaults.set(false, forKey: ScanProgressPreference.key)
    precondition(SelectedProtectionProfilePreference.save(.builtIn, defaults: defaults))
    guard let restarted = UserDefaults(suiteName: suite) else { fatalError("Restart suite unavailable") }
    precondition(restarted.synchronize())
    precondition(SelectedProtectionProfilePreference.selected(defaults: restarted) == .builtIn)
    precondition(restarted.string(forKey: key) == "built-in")
    precondition(restarted.string(forKey: "unrelatedPreference") == "custom-browser")
    precondition(ScanProgressPreference.isEnabled(defaults: restarted) == false)

    // General presentation reset must not clear the active profile.
    precondition(GeneralPreferencesReset.reset(defaults: defaults))
    precondition(defaults.string(forKey: key) == "built-in")

    // Future, malformed, and invalid profile values must remain unchanged;
    // the caller can report them, but may never pretend another policy is active.
    for invalid in ["unknown-policy", "", "disabled"] {
      defaults.set(invalid, forKey: key)
      precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == nil)
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(defaults.string(forKey: key) == invalid)
    }
    defaults.set(true, forKey: key)
    precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == nil)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.object(forKey: key) as? Bool == true)
    precondition(SelectedProtectionProfilePreference.selected(defaults: nil) == nil)
    precondition(!SelectedProtectionProfilePreference.save(.builtIn, defaults: nil))

    // Explicit profile must round-trip through the existing versioned schema;
    // old payloads remain compatible without an implicit new field.
    let legacy = try PDFMagicConfigurationSchema.decoded(from:
      Data(#"{"schemaVersion":1,"showScanProgress":false}"#.utf8))
    precondition(legacy.selectedProtectionProfile == nil)
    let selected = PDFMagicConfigurationSchema(
      showScanProgress: false, selectedProtectionProfile: .builtIn)
    let roundTrip = try PDFMagicConfigurationSchema.decoded(from: selected.encoded())
    precondition(roundTrip == selected)
    let json = String(decoding: try selected.encoded(), as: UTF8.self)
    precondition(json.contains(#""selectedProtectionProfile":"built-in""#))
    for invalid in [
      #"{"schemaVersion":1,"selectedProtectionProfile":"unknown-policy"}"#,
      #"{"schemaVersion":1,"selectedProtectionProfile":true}"#,
      #"{"schemaVersion":2,"selectedProtectionProfile":"built-in"}"#
    ] {
      do {
        _ = try PDFMagicConfigurationSchema.decoded(from: Data(invalid.utf8))
        fatalError("Unsupported configuration was accepted")
      } catch is DecodingError {}
    }

    // Legacy snapshot captures explicit stored choices without writing values.
    defaults.set("built-in", forKey: key)
    let snapshot = try PDFMagicConfigurationMigration.snapshotLegacyPreferences(defaults: defaults)
    let snapshotSchema = try PDFMagicConfigurationSchema.decoded(from: snapshot)
    precondition(snapshotSchema.selectedProtectionProfile == .builtIn)
    defaults.set("unknown-policy", forKey: key)
    do {
      _ = try PDFMagicConfigurationMigration.snapshotLegacyPreferences(defaults: defaults)
      fatalError("Unknown saved profile was silently rewritten")
    } catch PDFMagicConfigurationMigration.Failure.invalidLegacyValue(let badKey) {
      precondition(badKey == key)
      precondition(defaults.string(forKey: key) == "unknown-policy")
    }

    // In-memory recovery retains a valid selection, never edits source bytes.
    let malformed = Data(#"{"schemaVersion":1,"showScanProgress":"bad","selectedProtectionProfile":"built-in"}"#.utf8)
    guard case let .recovered(recovered) = try MalformedConfigurationRecovery.decode(malformed) else {
      fatalError("Expected explicit non-destructive recovery")
    }
    precondition(recovered.selectedProtectionProfile == .builtIn)
    precondition(malformed == Data(#"{"schemaVersion":1,"showScanProgress":"bad","selectedProtectionProfile":"built-in"}"#.utf8))
    print("Selected protection profile persistence tests passed")
  }
}

