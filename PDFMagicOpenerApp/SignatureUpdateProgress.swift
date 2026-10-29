import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

// An indeterminate indicator for a *live* FreshClam updater process.
// This metadata never authorizes scanning, declares definitions current,
// or infers a download percentage from untrusted updater output.
struct SignatureUpdateProgress {
  let startedAt: Date

  static func readInstalled(now: Date = Date()) -> SignatureUpdateProgress? {
    let signatures = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Application Support/Studio/allow-and-open/signatures",
                            isDirectory: true)
    return read(from: signatures, now: now)
  }

  // Only trust a bounded, plain record and a currently alive PID. The time
  // window keeps an orphaned marker from appearing to run indefinitely if
  // an unrelated process later reuses the same PID.
  static func read(from directory: URL, now: Date = Date()) -> SignatureUpdateProgress? {
    let marker = directory.appendingPathComponent("update-in-progress")
    let descriptor = open(marker.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
    guard descriptor >= 0 else { return nil }
    defer { close(descriptor) }
    var metadata = stat()
    guard fstat(descriptor, &metadata) == 0,
          (metadata.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG),
          metadata.st_size > 0, metadata.st_size <= 48 else { return nil }

    var bytes = [UInt8](repeating: 0, count: 48)
    let count = bytes.withUnsafeMutableBytes { buffer in
      #if canImport(Darwin)
      return Darwin.read(descriptor, buffer.baseAddress, buffer.count)
      #else
      return Glibc.read(descriptor, buffer.baseAddress, buffer.count)
      #endif
    }
    guard Int64(count) == metadata.st_size,
          let raw = String(bytes: bytes.prefix(Int(count)), encoding: .ascii),
          let match = raw.range(of: #"^[0-9]{1,12} [1-9][0-9]{0,9}\n?$"#,
                                options: .regularExpression),
          match == raw.startIndex..<raw.endIndex else { return nil }
    let fields = raw.trimmingCharacters(in: .newlines).split(separator: " ")
    guard fields.count == 2,
          let seconds = TimeInterval(fields[0]), seconds.isFinite,
          let pid = Int32(fields[1]), pid > 0,
          seconds > 0, seconds <= now.timeIntervalSince1970,
          now.timeIntervalSince1970 - seconds <= 2 * 60 * 60 else { return nil }
    // kill(pid, 0) is only a non-mutating liveness check: no signals are sent.
    guard kill(pid, 0) == 0 || errno == EPERM else { return nil }
    return SignatureUpdateProgress(startedAt: Date(timeIntervalSince1970: seconds))
  }
}
