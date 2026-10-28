import Foundation

func check(_ condition: @autoclosure () -> Bool, _ message: String) {
  if !condition() { fatalError(message) }
}

@main
struct ConfigurationSchemaTests {
  static func main() throws {
    let empty = PDFMagicConfigurationSchema()
    check(empty.schemaVersion == 1, "version must begin at one")
    check(empty.showScanProgress == nil, "legacy progress preference must be unset")
    check(empty.showSuccessfulScanNotifications == nil, "legacy notification preference must be unset")
    let emptyJSON = try empty.encoded()
    let emptyDictionary = try JSONSerialization.jsonObject(with: emptyJSON) as! [String: Any]
    check(emptyDictionary["schemaVersion"] as? Int == 1, "version must be serialized")
    check(emptyDictionary["showScanProgress"] == nil, "unset settings must not be materialized")

    let explicit = PDFMagicConfigurationSchema(
      showScanProgress: false, showSuccessfulScanNotifications: true
    )
    check(try PDFMagicConfigurationSchema.decoded(from: explicit.encoded()) == explicit,
          "explicit choices must round-trip")
    let oldVersion = Data(#"{"schemaVersion":0,"showScanProgress":true}"#.utf8)
    let futureVersion = Data(#"{"schemaVersion":2,"showScanProgress":true}"#.utf8)
    let missingVersion = Data(#"{"showScanProgress":true}"#.utf8)
    let malformed = Data(#"{"schemaVersion":1,"showScanProgress":"false"}"#.utf8)
    for invalid in [oldVersion, futureVersion, missingVersion, malformed] {
      do {
        _ = try PDFMagicConfigurationSchema.decoded(from: invalid)
        fatalError("invalid configuration must be rejected")
      } catch is DecodingError {
        // Expected: never reinterpret incompatible configuration as valid.
      }
    }
    let withUnknownKey = Data(
      #"{"schemaVersion":1,"showScanProgress":false,"futureChoice":"keep"}"#.utf8
    )
    check(try PDFMagicConfigurationSchema.decoded(from: withUnknownKey).showScanProgress == false,
          "additive keys should not break older readers")
    let suiteName = "local.studio.pdf-magic-opener.schema-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else { fatalError("test suite") }
    defer { defaults.removePersistentDomain(forName: suiteName) }
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    _ = try PDFMagicConfigurationSchema.decoded(from: explicit.encoded())
    check(ScanProgressPreference.isEnabled(defaults: defaults) == false,
          "schema decoding must not reset progress customization")
    check(SuccessfulScanNotificationPreference.isEnabled(defaults: defaults) == true,
          "schema decoding must not reset notification customization")
    print("Versioned configuration schema tests passed")
  }
}
