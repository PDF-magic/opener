import Foundation

@main
struct MalformedConfigurationRecoveryTests {
  static func main() throws {
    func bytes(_ text: String) -> Data { Data(text.utf8) }
    let valid = bytes(#"{"schemaVersion":1,"showScanProgress":false,"showBlockedFileNotifications":true,"futureSetting":"kept"}"#)
    guard case let .loaded(saved) = try MalformedConfigurationRecovery.decode(valid) else {
      fatalError("Valid configuration misclassified")
    }
    precondition(saved.showScanProgress == false)
    precondition(saved.showBlockedFileNotifications == true)
    let partial = bytes(#"{"schemaVersion":1,"showScanProgress":1,"showSuccessfulScanNotifications":true,"showBlockedFileNotifications":false}"#)
    guard case let .recovered(repaired) = try MalformedConfigurationRecovery.decode(partial) else {
      fatalError("Invalid type did not trigger recovery")
    }
    precondition(repaired.showScanProgress == nil)
    precondition(repaired.showSuccessfulScanNotifications == true)
    precondition(repaired.showBlockedFileNotifications == false)
    let truncated = bytes(#"{"schemaVersion":1,"showScanProgress":false"#)
    let original = truncated
    guard case let .recovered(defaults) = try MalformedConfigurationRecovery.decode(truncated) else {
      fatalError("Malformed JSON did not recover")
    }
    precondition(defaults.showScanProgress == nil)
    precondition(truncated == original)
    for damaged in [Data(), Data([0xFF]), bytes("[]"), bytes(#"{"showScanProgress":true}"#),
                    bytes(#"{"schemaVersion":true,"showScanProgress":1}"#)] {
      guard case .recovered = try MalformedConfigurationRecovery.decode(damaged) else {
        fatalError("Malformed input accepted")
      }
    }
    for version in [0, -1, 2] {
      do {
        _ = try MalformedConfigurationRecovery.decode(bytes("{\"schemaVersion\":\(version)}"))
        fatalError("Unsupported version recovered as defaults")
      } catch MalformedConfigurationRecovery.RecoveryError.unsupportedVersion(let actual) {
        precondition(actual == version)
      }
    }
    do {
      _ = try MalformedConfigurationRecovery.decode(Data(repeating: 0x20, count: 65_537))
      fatalError("Oversized input accepted")
    } catch MalformedConfigurationRecovery.RecoveryError.oversized {}
    let suite = "local.studio.pdf-magic-opener.recovery-test.\(UUID().uuidString)"
    guard let custom = UserDefaults(suiteName: suite) else { fatalError("Missing isolated suite") }
    defer { custom.removePersistentDomain(forName: suite) }
    custom.set(false, forKey: ScanProgressPreference.key)
    custom.set("my.custom.browser", forKey: "existingBrowserChoice")
    _ = try MalformedConfigurationRecovery.decode(truncated)
    precondition(custom.object(forKey: ScanProgressPreference.key) as? Bool == false)
    precondition(custom.string(forKey: "existingBrowserChoice") == "my.custom.browser")
    print("Malformed configuration recovery tests passed")
  }
}
