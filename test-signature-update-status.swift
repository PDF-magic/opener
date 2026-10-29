import Foundation

@main
struct SignatureUpdateStatusTests {
  static func main() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("signature-update-ui-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }

    let now = Date(timeIntervalSince1970: 1_700_000_100)
    let attempt = root.appendingPathComponent("last-attempted-update")
    let success = root.appendingPathComponent("last-successful-update")
    func write(_ url: URL, _ content: String) throws {
      try content.write(to: url, atomically: true, encoding: .ascii)
    }
    var report = SignatureUpdateStatus.read(from: root, now: now)
    precondition(report.lastAttempt == nil && report.lastSuccess == nil)
    precondition(report.message == "Update history unavailable")

    try write(success, "1700000000\n")
    report = SignatureUpdateStatus.read(from: root, now: now)
    precondition(report.lastAttempt == nil)
    precondition(report.lastSuccess == Date(timeIntervalSince1970: 1_700_000_000))
    precondition(report.message == "Successful update recorded; attempt history unavailable")

    try write(attempt, "1700000001\n")
    report = SignatureUpdateStatus.read(from: root, now: now)
    precondition(report.lastAttempt == Date(timeIntervalSince1970: 1_700_000_001))
    precondition(report.message == "Latest attempt is not confirmed successful")
    let originalSuccess = try String(contentsOf: success)
    precondition(originalSuccess == "1700000000\n")

    try write(success, "1700000001\n")
    report = SignatureUpdateStatus.read(from: root, now: now)
    precondition(report.message == "Successful update recorded")

    for invalid in ["", "NaN", "inf", "-1", "0", "not-a-date",
                    "1700000101", "2026-10-28T12:00Z", "1\n2", String(repeating: "1", count: 80)] {
      try write(attempt, invalid)
      report = SignatureUpdateStatus.read(from: root, now: now)
      precondition(report.lastAttempt == nil, "Unexpectedly accepted invalid timestamp")
      precondition(report.lastSuccess != nil)
    }

    try FileManager.default.removeItem(at: attempt)
    let outside = root.appendingPathComponent("private-data")
    try write(outside, "1700000001\n")
    try FileManager.default.createSymbolicLink(at: attempt, withDestinationURL: outside)
    report = SignatureUpdateStatus.read(from: root, now: now)
    precondition(report.lastAttempt == nil, "Symlinks must not be read")
    let originalOutside = try String(contentsOf: outside)
    precondition(originalOutside == "1700000001\n")

    try FileManager.default.removeItem(at: attempt)
    try FileManager.default.createDirectory(at: attempt, withIntermediateDirectories: false)
    precondition(SignatureUpdateStatus.read(from: root, now: now).lastAttempt == nil)

    // This view must never change the success marker or start an updater.
    let finalSuccess = try String(contentsOf: success)
    precondition(finalSuccess == "1700000001\n")
    print("PASS: signature update UI reads safe, independent timestamps without writing")
  }
}
