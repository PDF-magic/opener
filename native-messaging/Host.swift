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

  private static func response(for data: Data) throws -> Data {
    guard let message = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          Set(message.keys) == expectedFields,
          let version = message["version"] as? NSNumber,
          CFGetTypeID(version) != CFBooleanGetTypeID(),
          // JSON version 1 must be an integer, not 1.0 or 1e0 rounded to 1.
          ["c", "C", "s", "S", "i", "I", "l", "L", "q", "Q"].contains(
            String(cString: version.objCType)),
          version.intValue == 1 && version.doubleValue == 1,
          let kind = message["kind"] as? String, kind == "request",
          let topic = message["topic"] as? String, topic == "host.ping",
          let requestId = message["requestId"] as? String,
          isValidRequestId(requestId),
          message["payload"] is NSNull else {
      throw HostError.invalidMessage
    }

    // A transport liveness response is not an authenticated session, scan verdict,
    // permission grant, or authorization to open any PDF.
    let reply: [String: Any] = [
      "version": 1,
      "kind": "response",
      "topic": "host.ping",
      "requestId": requestId,
      "payload": ["status": "transport-only", "scanAvailable": false]
    ]
    let encoded = try JSONSerialization.data(withJSONObject: reply, options: [.sortedKeys])
    guard encoded.count <= maximumFrameBytes else { throw HostError.invalidMessage }
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
      while let request = try readFrame() {
        try writeFrame(response(for: request))
      }
    } catch {
      // No stderr or stdout diagnostics: native paths and user data must not leak.
      exit(1)
    }
  }
}
