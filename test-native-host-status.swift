import Foundation

// Isolated fixtures exercise bundle metadata and active-policy resolution.
// No persistent user settings are read or written by this test.
@main
struct NativeHostStatusTests {
  static func fixture(_ root: URL, name: String, identifier: String,
                      version: Any?) throws -> URL {
    let app = root.appendingPathComponent(name + ".app", isDirectory: true)
    let contents = app.appendingPathComponent("Contents", isDirectory: true)
    try FileManager.default.createDirectory(at: contents,
                                            withIntermediateDirectories: true)
    var metadata: [String: Any] = [
      "CFBundleIdentifier": identifier,
      "CFBundlePackageType": "APPL",
      "CFBundleExecutable": "PDFMagicOpener"
    ]
    if let version { metadata["CFBundleShortVersionString"] = version }
    let data = try PropertyListSerialization.data(
      fromPropertyList: metadata, format: .xml, options: 0
    )
    try data.write(to: contents.appendingPathComponent("Info.plist"))
    return app
  }

  static func main() throws {
    let root = FileManager.default.temporaryDirectory.appendingPathComponent(
      "native-status-fixtures-" + UUID().uuidString, isDirectory: true
    )
    try FileManager.default.createDirectory(at: root,
                                            withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let identifier = NativeHostStatus.applicationBundleIdentifier
    let good = try fixture(root, name: "valid", identifier: identifier, version: "7.8.9")
    let wrong = try fixture(root, name: "wrong-id", identifier: "invalid.other.app",
                            version: "99.99")
    let missing = try fixture(root, name: "missing-version", identifier: identifier,
                              version: nil)
    let invalid = try fixture(root, name: "invalid-version", identifier: identifier,
                              version: "bad\nversion")
    let numeric = try fixture(root, name: "numeric-version", identifier: identifier,
                              version: 123)

    precondition(NativeHostStatus.applicationVersion(at: good) == "7.8.9")
    for path in [wrong, missing, invalid, numeric] {
      precondition(NativeHostStatus.applicationVersion(at: path) == nil)
    }
    precondition(NativeHostStatus.applicationVersion(at: nil) == nil)
    precondition(NativeHostStatus.applicationVersion(
      at: root.appendingPathComponent("not-installed.app")) == nil)

    precondition(NativeHostStatus.effectiveProfile(from: nil) == "built-in")
    precondition(NativeHostStatus.effectiveProfile(from: "built-in") == "built-in")
    for unsupported: Any in ["standard", "enhanced", "maximum", "custom", 1, true] {
      precondition(NativeHostStatus.effectiveProfile(from: unsupported) == nil)
    }

    let available = NativeHostStatus.snapshot(appURL: good, savedSelection: nil)
    precondition(available["applicationVersion"] as? String == "7.8.9")
    precondition(available["protocolVersion"] as? Int == 1)
    precondition(available["activeProtectionProfile"] as? String == "built-in")
    precondition(available["scanAvailable"] as? Bool == false)
    precondition(available["status"] as? String == "transport-only")

    let unavailable = NativeHostStatus.snapshot(
      appURL: nil, savedSelection: "maximum"
    )
    precondition(unavailable["applicationVersion"] is NSNull)
    precondition(unavailable["activeProtectionProfile"] is NSNull)
    let inaccessible = NativeHostStatus.snapshot(
      appURL: good, savedSelection: nil, preferencesAvailable: false
    )
    precondition(inaccessible["activeProtectionProfile"] is NSNull)
    precondition(inaccessible["applicationVersion"] as? String == "7.8.9")
  }
}
