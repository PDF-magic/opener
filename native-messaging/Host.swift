import CoreFoundation
import Foundation

// A standalone, transport-only WebExtensions native messaging process.
// It must never scan, open, or authorize a document.
private enum HostError: Error {
  case invalidMessage
}

@main
struct PDFMagicNativeMessagingHost {
  private static let maximumFrameBytes = 16 * 1024
  private static let expectedFields: Set<String> = [
    "version", "kind", "topic", "requestId", "payload"
  ]

  private static func readExactly(_ count: Int, allowCleanEOF: Bool) throws -> Data? {
    var result = Data()
    while result.count < count {
      let chunk = FileHandle.standardInput.readData(ofLength: count - result.count)
      if chunk.isEmpty {
        if allowCleanEOF && result.isEmpty { return nil }
        throw HostError.invalidMessage
      }
      result.append(chunk)
    }
    return result
  }

  private static func readFrame() throws -> Data? {
    guard let header = try readExactly(4, allowCleanEOF: true) else { return nil }
    let size = header.enumerated().reduce(UInt32(0)) { result, element in
      result | (UInt32(element.element) << (8 * element.offset))
    }
    guard size > 0 && size <= maximumFrameBytes else { throw HostError.invalidMessage }
    return try readExactly(Int(size), allowCleanEOF: false)
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

  private static func writeFrame(_ data: Data) {
    let size = UInt32(data.count)
    let prefix = Data([
      UInt8(truncatingIfNeeded: size),
      UInt8(truncatingIfNeeded: size >> 8),
      UInt8(truncatingIfNeeded: size >> 16),
      UInt8(truncatingIfNeeded: size >> 24)
    ])
    FileHandle.standardOutput.write(prefix)
    FileHandle.standardOutput.write(data)
  }

  static func main() {
    do {
      // Connection-local only; a new host process starts with no handshake.
      var handshakeComplete = false
      while let request = try readFrame() {
        try writeFrame(response(for: request, handshakeComplete: &handshakeComplete))
      }
    } catch {
      // No stderr or stdout diagnostics: native paths and user data must not leak.
      exit(1)
    }
  }
}
