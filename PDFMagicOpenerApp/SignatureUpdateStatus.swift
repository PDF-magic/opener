import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

// Read only the two timestamp records written by the installed FreshClam
// updater. This is display metadata, never a substitute for the scan gate's
// signature freshness, database validity, or malware verdict checks.
struct SignatureUpdateStatus {
  let lastAttempt: Date?
  let lastSuccess: Date?
  let lastFailure: Date?
  let failureReason: String?

  var failureExplanation: String? {
    switch failureReason {
    case "updater-unavailable":
      return "The installed FreshClam updater was unavailable. Definitions may be outdated."
    case "freshclam-error":
      return "FreshClam did not finish successfully. Definitions may be outdated."
    case "incomplete-download":
      return "Incomplete ClamAV signature download detected. Definitions may be outdated."
    default:
      return nil
    }
  }

  var hasUnresolvedFailure: Bool {
    guard let failure = lastFailure else { return false }
    return lastSuccess == nil || failure >= lastSuccess!
  }

  var message: String {
    if hasUnresolvedFailure { return "Signature update failure recorded; a later success is not confirmed" }
    switch (lastAttempt, lastSuccess) {
    case (nil, nil):
      return "Update history unavailable"
    case (nil, .some):
      return "Successful update recorded; attempt history unavailable"
    case (.some, nil):
      return "Latest attempt has no recorded success"
    case let (.some(attempt), .some(success)) where attempt > success:
      return "Latest attempt is not confirmed successful"
    case (.some, .some):
      return "Successful update recorded"
    }
  }

  static func readInstalled(now: Date = Date()) -> SignatureUpdateStatus {
    let signatures = FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Application Support/Studio/allow-and-open/signatures",
                            isDirectory: true)
    return read(from: signatures, now: now)
  }

  // Exposed internally so native regressions can use isolated temporary data.
  static func read(from directory: URL, now: Date = Date()) -> SignatureUpdateStatus {
    let failure = readFailure(directory.appendingPathComponent("last-failed-update"), now: now)
    return SignatureUpdateStatus(
      lastAttempt: readStamp(directory.appendingPathComponent("last-attempted-update"), now: now),
      lastSuccess: readStamp(directory.appendingPathComponent("last-successful-update"), now: now),
      lastFailure: failure?.time,
      failureReason: failure?.reason
    )
  }


  // Fixed-token failure records written atomically by the updater. Treat all
  // other content as unknown. No raw FreshClam output enters this view.
  private static func readFailure(_ url: URL, now: Date) -> (time: Date, reason: String)? {
    let descriptor = open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
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
          let match = raw.range(of: #"^[0-9]{1,12} (freshclam-error|updater-unavailable|incomplete-download)\n?$"#,
                                options: .regularExpression),
          match == raw.startIndex..<raw.endIndex else { return nil }
    let fields = raw.trimmingCharacters(in: .newlines).split(separator: " ")
    guard fields.count == 2,
          let seconds = Double(fields[0]),
          seconds.isFinite, seconds > 0,
          seconds <= now.timeIntervalSince1970 else { return nil }
    return (Date(timeIntervalSince1970: seconds), String(fields[1]))
  }

  private static func readStamp(_ url: URL, now: Date) -> Date? {
    let descriptor = open(url.path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
    guard descriptor >= 0 else { return nil }
    defer { close(descriptor) }
    var metadata = stat()
    guard fstat(descriptor, &metadata) == 0,
          (metadata.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else {
      return nil
    }

    // Read a bounded ASCII timestamp, never arbitrary scanner logs or files.
    var bytes = [UInt8](repeating: 0, count: 48)
    let count = bytes.withUnsafeMutableBytes { buffer in
      #if canImport(Darwin)
      return Darwin.read(descriptor, buffer.baseAddress, buffer.count)
      #else
      return Glibc.read(descriptor, buffer.baseAddress, buffer.count)
      #endif
    }
    guard count > 0,
          let raw = String(bytes: bytes.prefix(Int(count)), encoding: .ascii),
          let match = raw.range(of: #"^[0-9]{1,12}(\.[0-9]{1,6})?\n?$"#,
                                options: .regularExpression),
          match == raw.startIndex..<raw.endIndex,
          let seconds = Double(raw.trimmingCharacters(in: .newlines)),
          seconds.isFinite,
          seconds > 0,
          seconds <= now.timeIntervalSince1970 else {
      return nil
    }
    return Date(timeIntervalSince1970: seconds)
  }
}
