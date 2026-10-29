import Foundation

@main
struct SignatureUpdateFailureTests {
  static func main() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("signature-failure-ui-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let now = Date(timeIntervalSince1970: 1_700_000_100)
    let failure = root.appendingPathComponent("last-failed-update")
    let success = root.appendingPathComponent("last-successful-update")
    func write(_ file: URL, _ contents: String) throws {
      try contents.write(to: file, atomically: true, encoding: .ascii)
    }
    var info = SignatureUpdateStatus.read(from: root, now: now)
    precondition(info.lastFailure == nil && !info.hasUnresolvedFailure)

    try write(failure, "1700000010 freshclam-error\n")
    info = SignatureUpdateStatus.read(from: root, now: now)
    precondition(info.lastFailure == Date(timeIntervalSince1970: 1_700_000_010))
    precondition(info.hasUnresolvedFailure)
    precondition(info.message.contains("failure recorded"))
    precondition(info.failureExplanation?.contains("FreshClam") == true)

    try write(success, "1700000011\n")
    info = SignatureUpdateStatus.read(from: root, now: now)
    precondition(!info.hasUnresolvedFailure, "Later success must supersede failure")
    precondition(info.lastFailure != nil, "Historical failures remain visible")
    precondition(info.message == "Successful update recorded; attempt history unavailable")

    try write(failure, "1700000012 updater-unavailable\n")
    info = SignatureUpdateStatus.read(from: root, now: now)
    precondition(info.hasUnresolvedFailure)
    precondition(info.failureExplanation?.contains("unavailable") == true)

    try write(failure, "1700000013 incomplete-download\n")
    info = SignatureUpdateStatus.read(from: root, now: now)
    precondition(info.hasUnresolvedFailure)
    precondition(info.failureReason == "incomplete-download")
    precondition(info.failureExplanation?.contains("Incomplete") == true)

    for malformed in [
      "", "1700000012 raw private/path", "1700000012 unknown",
      "1700000101 freshclam-error", "NaN freshclam-error",
      "-1 freshclam-error", "1700000012 freshclam-error\nsecond",
      "1700000012 freshclam-error and secret",
      String(repeating: "1", count: 70)
    ] {
      try write(failure, malformed)
      info = SignatureUpdateStatus.read(from: root, now: now)
      precondition(info.lastFailure == nil, "Invalid or private failure record accepted")
      precondition(!info.hasUnresolvedFailure)
    }

    try FileManager.default.removeItem(at: failure)
    let outside = root.appendingPathComponent("private-data")
    try write(outside, "1700000012 freshclam-error\n")
    try FileManager.default.createSymbolicLink(at: failure, withDestinationURL: outside)
    precondition(SignatureUpdateStatus.read(from: root, now: now).lastFailure == nil)
    try FileManager.default.removeItem(at: failure)
    try FileManager.default.createDirectory(at: failure, withIntermediateDirectories: false)
    precondition(SignatureUpdateStatus.read(from: root, now: now).lastFailure == nil)
    let stamp = try String(contentsOf: success, encoding: .ascii)
    precondition(stamp == "1700000011\n")
    print("PASS: native failure display is independent, sanitized and read-only")
  }
}
