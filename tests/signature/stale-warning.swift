import Foundation

@main
struct StaleSignatureWarningTests {
  static func main() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("stale-signature-warning-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let now = Date(timeIntervalSince1970: 1_700_200_000)
    let stamp = root.appendingPathComponent("last-successful-update")
    func read(_ value: String?) throws -> SignatureUpdateStatus {
      if let value {
        try value.write(to: stamp, atomically: true, encoding: .ascii)
      } else {
        try? FileManager.default.removeItem(at: stamp)
      }
      return SignatureUpdateStatus.read(from: root, now: now)
    }
    func epoch(_ age: Int) -> String {
      String(Int(now.timeIntervalSince1970) - age) + "\n"
    }

    precondition(SignatureUpdateStatus.maximumSignatureAge == 48 * 60 * 60)
    var observed = try read(nil)
    precondition(observed.freshnessWarning(now: now)?.contains("cannot be verified") == true)

    for age in [0, 1, 24 * 60 * 60, 48 * 60 * 60 - 1, 48 * 60 * 60] {
      observed = try read(epoch(age))
      precondition(observed.freshnessWarning(now: now) == nil,
                   "A valid timestamp within the inclusive 48-hour window must not be stale")
    }

    for age in [48 * 60 * 60 + 1, 49 * 60 * 60, 72 * 60 * 60] {
      observed = try read(epoch(age))
      let warning = observed.freshnessWarning(now: now)
      precondition(warning?.contains("more than 48 hours old") == true,
                   "Old signatures must be explicitly identified")
      precondition(warning?.contains("Scanner freshness checks remain enforced") == true)
    }

    for invalid in ["", "NaN", "inf", "-1", "garbled",
                    String(Int(now.timeIntervalSince1970) + 1) + "\n",
                    "2026-10-28T12:00Z"] {
      observed = try read(invalid)
      precondition(observed.lastSuccess == nil)
      precondition(observed.freshnessWarning(now: now)?.contains("cannot be verified") == true,
                   "Unknown timestamp must not be presented as fresh")
    }

    observed = try read(epoch(10))
    precondition(observed.freshnessWarning(now: now.addingTimeInterval(-20))?
      .contains("current clock") == true, "Backward clock jump requires uncertainty")

    try FileManager.default.removeItem(at: stamp)
    let external = root.appendingPathComponent("other-file")
    try epoch(70 * 60 * 60).write(to: external, atomically: true, encoding: .ascii)
    try FileManager.default.createSymbolicLink(at: stamp, withDestinationURL: external)
    observed = SignatureUpdateStatus.read(from: root, now: now)
    precondition(observed.lastSuccess == nil)
    precondition(observed.freshnessWarning(now: now)?.contains("cannot be verified") == true)

    try FileManager.default.removeItem(at: stamp)
    try FileManager.default.createDirectory(at: stamp, withIntermediateDirectories: false)
    observed = SignatureUpdateStatus.read(from: root, now: now)
    precondition(observed.lastSuccess == nil)
    precondition(observed.freshnessWarning(now: now)?.contains("cannot be verified") == true)
    print("PASS: 48-hour inclusive warning boundary and safe unknown statuses")
  }
}
