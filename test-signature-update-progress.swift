import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

@main
struct SignatureUpdateProgressTests {
  static func main() throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("signature-progress-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let marker = root.appendingPathComponent("update-in-progress")
    let now = Date(timeIntervalSince1970: 1_700_000_000)
    func put(_ raw: String) throws {
      try raw.write(to: marker, atomically: true, encoding: .ascii)
    }
    precondition(SignatureUpdateProgress.read(from: root, now: now) == nil)
    let live = "1699999999 \(getpid())\n"
    try put(live)
    let status = SignatureUpdateProgress.read(from: root, now: now)
    precondition(status?.startedAt == Date(timeIntervalSince1970: 1_699_999_999))

    for invalid in ["", "1700000001 \(getpid())", "1699999999 0",
                    "1699999999 -1", "NaN \(getpid())",
                    "1699999999 \(getpid()) garbage", "1699999999 \(getpid())\n2",
                    String(repeating: "1", count: 64)] {
      try put(invalid)
      precondition(SignatureUpdateProgress.read(from: root, now: now) == nil)
    }
    try put("1699999999 2147483647\n")
    precondition(SignatureUpdateProgress.read(from: root, now: now) == nil)
    try put(live)
    precondition(SignatureUpdateProgress.read(
      from: root, now: Date(timeIntervalSince1970: 1_700_010_000)) == nil)

    try FileManager.default.removeItem(at: marker)
    let outside = root.appendingPathComponent("external")
    try live.write(to: outside, atomically: true, encoding: .ascii)
    try FileManager.default.createSymbolicLink(at: marker, withDestinationURL: outside)
    precondition(SignatureUpdateProgress.read(from: root, now: now) == nil)
    let originalOutside = try String(contentsOf: outside)
    precondition(originalOutside == live)
    try FileManager.default.removeItem(at: marker)
    try FileManager.default.createDirectory(at: marker, withIntermediateDirectories: false)
    precondition(SignatureUpdateProgress.read(from: root, now: now) == nil)
    print("PASS: bounded live update metadata and stale, malformed, symlink markers")
  }
}
