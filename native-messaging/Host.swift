import CoreFoundation
import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif


// Bound request volume before JSON parsing and response generation. Every
// complete frame consumes a slot, including ping and handshake requests.
// A burst over budget terminates only this process without a protocol reply.
private struct NativeRequestRateLimiter {
  static let maximumRequests = 64
  static let windowSeconds: TimeInterval = 2
  private var acceptedAt: [TimeInterval] = []

  mutating func allow(now: TimeInterval) -> Bool {
    // A bounded sliding window prevents edge-of-window double bursts.
    acceptedAt.removeAll { now - $0 >= Self.windowSeconds }
    guard acceptedAt.count < Self.maximumRequests else { return false }
    acceptedAt.append(now)
    return true
  }
}

// A standalone, transport-only WebExtensions native messaging process.
// It must never scan, open, or authorize a document.
private enum HostError: Error {
  case invalidMessage
}

@main
struct PDFMagicNativeMessagingHost {
  private static let maximumFrameBytes = 16 * 1024
  // A silent peer cannot hold the process forever. Both frame completion
  // and response writing use fixed, cumulative monotonic deadlines.
  private static let idleTimeoutSeconds: TimeInterval = 10
  private static let frameTimeoutSeconds: TimeInterval = 5
  private static let responseTimeoutSeconds: TimeInterval = 5
  // One overall limit per request, including idle, frame, dispatch and reply.
  // Individual transport deadlines remain more restrictive where applicable.
  private static let requestTimeoutSeconds: TimeInterval = 15
  private static let expectedFields: Set<String> = [
    "version", "kind", "topic", "requestId", "payload"
  ]

  // Keep a separate allowlist for native message operations. A new switch
  // handler is unusable until its topic passes an explicit security review.
  // No message topic can select an executable, process or shell.
  private static let approvedTopics: Set<String> = [
    "host.handshake", "host.health", "host.ping",
    "scan.cancel", "scan.request", "scan.result", "scan.status"
  ]

  // Browser nativeMessaging starts one host process per port; process-local
  // counters do not constrain connections created by other browser processes.
  // Four advisory file-lock slots limit concurrent hosts for the *real* OS user.
  private static let maximumConcurrentConnections = 4
  private static let lockDirectoryName = ".pdf-magic-native-connections"
  // CoreFoundation and POSIX both export S_IF* on Linux Swift. Select the
  // platform-specific constants explicitly without altering lock admission.
  #if canImport(Darwin)
  private static let fileTypeMask = mode_t(Darwin.S_IFMT)
  private static let directoryFileType = mode_t(Darwin.S_IFDIR)
  private static let regularFileType = mode_t(Darwin.S_IFREG)
  #else
  private static let fileTypeMask = mode_t(Glibc.S_IFMT)
  private static let directoryFileType = mode_t(Glibc.S_IFDIR)
  private static let regularFileType = mode_t(Glibc.S_IFREG)
  #endif

  private static func acquireConnectionSlot() throws -> Int32 {
    guard let account = getpwuid(getuid()) else { throw HostError.invalidMessage }
    var home = String(cString: account.pointee.pw_dir)
    #if NATIVE_HOST_CONNECTION_TESTING
    // Test-only isolated home. Production builds cannot change the lock scope
    // through HOME, command-line arguments, messages or environment variables.
    if let testHome = ProcessInfo.processInfo.environment["PDF_MAGIC_NATIVE_TEST_HOME"] {
      home = testHome
    }
    #endif
    let directoryFlags = O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC
    let homeFD = open(home, directoryFlags)
    guard homeFD >= 0 else { throw HostError.invalidMessage }
    defer { close(homeFD) }
    var info = stat()
    guard fstat(homeFD, &info) == 0,
          (info.st_mode & fileTypeMask) == directoryFileType,
          info.st_uid == getuid() else { throw HostError.invalidMessage }

    // The lock directory and slots are user-owned and not accessible by
    // other accounts. Never follow symlinks or trust caller-chosen paths.
    if mkdirat(homeFD, lockDirectoryName, mode_t(0o700)) != 0 && errno != EEXIST {
      throw HostError.invalidMessage
    }
    let directoryFD = openat(homeFD, lockDirectoryName, directoryFlags)
    guard directoryFD >= 0 else { throw HostError.invalidMessage }
    defer { close(directoryFD) }
    guard fstat(directoryFD, &info) == 0,
          (info.st_mode & fileTypeMask) == directoryFileType,
          info.st_uid == getuid(),
          (info.st_mode & mode_t(0o077)) == 0 else {
      throw HostError.invalidMessage
    }

    // flock is released by the kernel on EOF/normal exit, process crash, or
    // kill; a stale slot file cannot permanently consume capacity.
    for index in 0..<maximumConcurrentConnections {
      let descriptor = openat(
        directoryFD, "slot-\(index).lock",
        O_RDWR | O_CREAT | O_NOFOLLOW | O_CLOEXEC, mode_t(0o600)
      )
      guard descriptor >= 0 else { throw HostError.invalidMessage }
      guard fstat(descriptor, &info) == 0,
            (info.st_mode & fileTypeMask) == regularFileType,
            info.st_uid == getuid(), info.st_nlink == 1,
            (info.st_mode & mode_t(0o077)) == 0 else {
        close(descriptor)
        throw HostError.invalidMessage
      }
      if flock(descriptor, LOCK_EX | LOCK_NB) == 0 {
        return descriptor
      }
      let failure = errno
      close(descriptor)
      if failure != EWOULDBLOCK && failure != EAGAIN {
        throw HostError.invalidMessage
      }
    }
    throw HostError.invalidMessage
  }

  private static func waitForIO(
    _ descriptor: Int32, events: Int16, deadline: TimeInterval
  ) throws {
    while true {
      let remaining = deadline - ProcessInfo.processInfo.systemUptime
      guard remaining > 0 else { throw HostError.invalidMessage }
      var entry = pollfd(fd: descriptor, events: events, revents: 0)
      let milliseconds = Int32(min(ceil(remaining * 1000), Double(Int32.max)))
      let ready = poll(&entry, 1, milliseconds)
      if ready < 0 && errno == EINTR { continue }
      if ready > 0 && (entry.revents & events) != 0 { return }
      // A peer closing its input is only a clean EOF between frames.
      // Allow read() to distinguish it from a truncated header or body.
      if ready > 0 && events == Int16(POLLIN) &&
          (entry.revents & Int16(POLLHUP)) != 0 { return }
      throw HostError.invalidMessage
    }
  }

  private static func readExactly(
    _ count: Int, allowCleanEOF: Bool, deadline: TimeInterval
  ) throws -> Data? {
    var result = Data()
    while result.count < count {
      try waitForIO(STDIN_FILENO, events: Int16(POLLIN), deadline: deadline)
      var buffer = [UInt8](repeating: 0, count: min(4096, count - result.count))
      let length = buffer.withUnsafeMutableBytes {
        read(STDIN_FILENO, $0.baseAddress, $0.count)
      }
      if length < 0 && (errno == EINTR || errno == EAGAIN) { continue }
      guard length >= 0 else { throw HostError.invalidMessage }
      if length == 0 {
        if allowCleanEOF && result.isEmpty { return nil }
        throw HostError.invalidMessage
      }
      result.append(contentsOf: buffer[..<length])
    }
    return result
  }

  private static func readFrame(requestDeadline: TimeInterval) throws -> Data? {
    // Idle waiting is separate from the entire active frame deadline.
    // Dripping bytes cannot reset the deadline for the length or body.
    guard let firstByte = try readExactly(
      1, allowCleanEOF: true,
      deadline: min(
        requestDeadline, ProcessInfo.processInfo.systemUptime + idleTimeoutSeconds
      )
    ) else { return nil }
    let deadline = min(
      requestDeadline, ProcessInfo.processInfo.systemUptime + frameTimeoutSeconds
    )
    guard let headerTail = try readExactly(
      3, allowCleanEOF: false, deadline: deadline
    ) else { throw HostError.invalidMessage }
    var header = firstByte
    header.append(headerTail)
    let size = header.enumerated().reduce(UInt32(0)) { result, element in
      result | (UInt32(element.element) << (8 * element.offset))
    }
    guard size > 0 && size <= maximumFrameBytes else { throw HostError.invalidMessage }
    return try readExactly(Int(size), allowCleanEOF: false, deadline: deadline)
  }

  private static func isValidRequestId(_ value: String) -> Bool {
    let bytes = Array(value.utf8)
    return !bytes.isEmpty && bytes.count <= 80 && bytes.allSatisfy { byte in
      (byte >= 65 && byte <= 90) || (byte >= 97 && byte <= 122) ||
      (byte >= 48 && byte <= 57) || byte == 45 || byte == 95
    }
  }

  private static func response(for data: Data, handshakeComplete: inout Bool) throws -> Data {
    guard let message = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          Set(message.keys) == expectedFields,
          let version = message["version"] as? NSNumber,
          CFGetTypeID(version) != CFBooleanGetTypeID(),
          // JSON version 1 must be an integer, not 1.0 or 1e0 rounded to 1.
          ["c", "C", "s", "S", "i", "I", "l", "L", "q", "Q"].contains(
            String(cString: version.objCType)),
          version.intValue == 1 && version.doubleValue == 1,
          let kind = message["kind"] as? String, kind == "request",
          let topic = message["topic"] as? String,
          approvedTopics.contains(topic),
          let requestId = message["requestId"] as? String,
          isValidRequestId(requestId) else {
      throw HostError.invalidMessage
    }

    let payload: [String: Any]
    switch topic {
    case "host.ping":
      // Preserve the existing read-only liveness probe before and after hello.
      guard message["payload"] is NSNull else { throw HostError.invalidMessage }
      payload = ["status": "transport-only", "scanAvailable": false]
    case "host.health":
      // Health is a read-only, post-handshake transport check. No scanner is
      // connected or inspected here; an acknowledged frame cannot establish
      // ClamAV health, a verified scan verdict, or permission to open a PDF.
      guard handshakeComplete, message["payload"] is NSNull else {
        throw HostError.invalidMessage
      }
      payload = [
        "status": "transport-only",
        "transportResponsive": true,
        "scannerHealth": NSNull(),
        "scanAvailable": false,
        "authorizesOpen": false
      ]
    case "host.handshake":
      // One version-1 handshake per process. Echoing a bounded challenge proves
      // correlation only: it does NOT authenticate the browser or host.
      guard !handshakeComplete,
            let hello = message["payload"] as? [String: Any],
            hello.count == 1,
            let clientNonce = hello["clientNonce"] as? String,
            (16...64).contains(clientNonce.utf8.count),
            isValidRequestId(clientNonce) else {
        throw HostError.invalidMessage
      }
      // Resolve locally installed metadata, not caller-supplied claims.
      // Unknown app versions and unsupported saved policy values stay null.
      var status = NativeHostStatus.current()
      status["clientNonce"] = clientNonce
      payload = status
    case "scan.request":
      // Define the request protocol without enabling a scan. A handshake is
      // transport readiness, never authentication or proof of a user gesture.
      // A trusted coordinator must separately select a local PDF and enforce
      // scanner, freshness, integrity, quarantine and opening requirements.
      guard handshakeComplete,
            let scanRequest = message["payload"] as? [String: Any],
            scanRequest.count == 1,
            let intent = scanRequest["intent"] as? String,
            intent == "user-selected-pdf" else {
        throw HostError.invalidMessage
      }
      // Do not accept paths, browser download metadata, file contents,
      // claimed verdicts, or caller-provided policy overrides. This reply
      // neither queues work nor confirms an actual scan was performed.
      payload = [
        "status": "unavailable",
        "reason": "trusted-scan-coordinator-required",
        "scanAvailable": false,
        "scanStarted": false,
        "scanVerified": false,
        "authorizesOpen": false
      ]
    case "scan.status":
      // A scan request is currently never submitted to a trusted coordinator.
      // A status lookup must be correlated but cannot invent a job, progress,
      // scanner verdict, or authorization. Even an unknown scan request ID
      // therefore receives the same truthful unavailable response.
      guard handshakeComplete,
            let statusQuery = message["payload"] as? [String: Any],
            statusQuery.count == 1,
            let scanRequestId = statusQuery["scanRequestId"] as? String,
            isValidRequestId(scanRequestId) else {
        throw HostError.invalidMessage
      }
      payload = [
        "scanRequestId": scanRequestId,
        "status": "unavailable",
        "reason": "trusted-scan-coordinator-required",
        "scanAvailable": false,
        "scanStarted": false,
        "scanVerified": false,
        "authorizesOpen": false
      ]
    case "scan.result":
      // The standalone host has no verified scan records or trusted scanner
      // coordinator. A correlated result query must never manufacture a
      // clean/malware/error verdict or imply that PDF opening is permitted.
      guard handshakeComplete,
            let resultQuery = message["payload"] as? [String: Any],
            resultQuery.count == 1,
            let scanRequestId = resultQuery["scanRequestId"] as? String,
            isValidRequestId(scanRequestId) else {
        throw HostError.invalidMessage
      }
      // Even a matching scan.request ID was rejected as unavailable; the
      // host does not store job identities or observe scanner subprocesses.
      payload = [
        "scanRequestId": scanRequestId,
        "status": "unavailable",
        "reason": "trusted-scan-coordinator-required",
        "result": NSNull(),
        "scanCompleted": false,
        "scanVerified": false,
        "authorizesOpen": false
      ]
    case "scan.cancel":
      // Cancellation is a distinct v1 message but cannot operate on a scan
      // until a trusted scanner coordinator is connected. A handshake or
      // matching scan ID is not proof that an actual job exists.
      guard handshakeComplete,
            let cancelRequest = message["payload"] as? [String: Any],
            cancelRequest.count == 1,
            let scanRequestId = cancelRequest["scanRequestId"] as? String,
            isValidRequestId(scanRequestId) else {
        throw HostError.invalidMessage
      }
      // Do not claim cancellation succeeded, terminate arbitrary processes,
      // or clear verified scan results. Never accept caller-supplied PIDs,
      // local file paths, signals, claimed verdicts, or policy overrides.
      payload = [
        "scanRequestId": scanRequestId,
        "status": "unavailable",
        "reason": "trusted-scan-coordinator-required",
        "cancellationAccepted": false,
        "cancelled": false,
        "scanStarted": false,
        "scanVerified": false,
        "authorizesOpen": false
      ]
    default:
      throw HostError.invalidMessage
    }

    // This is transport readiness, not a scan verdict or permission grant.
    let reply: [String: Any] = [
      "version": 1,
      "kind": "response",
      "topic": topic,
      "requestId": requestId,
      "payload": payload
    ]
    let encoded = try JSONSerialization.data(withJSONObject: reply, options: [.sortedKeys])
    guard encoded.count <= maximumFrameBytes else { throw HostError.invalidMessage }
    if topic == "host.handshake" { handshakeComplete = true }
    return encoded
  }

  private static func writeFrame(
    _ data: Data, requestDeadline: TimeInterval
  ) throws {
    let size = UInt32(data.count)
    var frame = Data([
      UInt8(truncatingIfNeeded: size),
      UInt8(truncatingIfNeeded: size >> 8),
      UInt8(truncatingIfNeeded: size >> 16),
      UInt8(truncatingIfNeeded: size >> 24)
    ])
    frame.append(data)
    let deadline = min(
      requestDeadline, ProcessInfo.processInfo.systemUptime + responseTimeoutSeconds
    )
    var offset = 0
    while offset < frame.count {
      try waitForIO(STDOUT_FILENO, events: Int16(POLLOUT), deadline: deadline)
      // Limit each pipe write to POSIX's minimum atomic PIPE_BUF size.
      // A blocked or disconnected receiver can never stall this loop.
      let length = frame.withUnsafeBytes { bytes in
        write(STDOUT_FILENO, bytes.baseAddress!.advanced(by: offset),
              min(512, frame.count - offset))
      }
      if length < 0 && (errno == EINTR || errno == EAGAIN) { continue }
      guard length > 0 else { throw HostError.invalidMessage }
      offset += length
    }
  }

  static func main() {
    // The independent origin-validation fixture suite tests the exact
    // browser origin rules, including its macOS home-directory requirements.
    // Integration fixtures exercise the separate exact native caller gate.
    // The production binary ALWAYS enforces both checks.
    #if !NATIVE_HOST_CONNECTION_TESTING
    guard NativeCallerOrigin.verifyProcessArguments() != .denied else { exit(1) }
    #endif
    do {
      // Validate the exact installed native host extension identity independently
      // of the browser's origin marker, before admitting a connection.
      guard NativeCallerAdmission.allows(Array(CommandLine.arguments.dropFirst())) else {
        exit(1)
      }
      // Admit before reading any caller input or emitting any protocol bytes.
      let slot = try acquireConnectionSlot()
      defer { close(slot) }
      // Connection-local only; a new host process starts with no handshake.
      var handshakeComplete = false
      var rateLimiter = NativeRequestRateLimiter()
      while true {
        let requestDeadline = ProcessInfo.processInfo.systemUptime +
          requestTimeoutSeconds
        guard let request = try readFrame(requestDeadline: requestDeadline) else { break }
        guard rateLimiter.allow(now: ProcessInfo.processInfo.systemUptime) else {
          throw HostError.invalidMessage
        }
        let reply = try response(for: request, handshakeComplete: &handshakeComplete)
        // Expiration is fatal even if a future handler performs slow work.
        guard ProcessInfo.processInfo.systemUptime < requestDeadline else {
          throw HostError.invalidMessage
        }
        try writeFrame(reply, requestDeadline: requestDeadline)
      }
    } catch {
      // No stderr or stdout diagnostics: native paths and user data must not leak.
      exit(1)
    }
  }
}
