import Foundation

@main
struct SafariNativeMessagingTests {
  static func main() {
    let request: [String: Any] = [
      "version": 1, "kind": "request", "topic": "native.status",
      "requestId": "status-123_A", "payload": NSNull()
    ]
    guard let reply = SafariNativeMessagingAdapter.reply(to: request),
          let payload = reply["payload"] as? [String: Any] else {
      fatalError("Valid native status request must receive a reply")
    }
    precondition(reply.count == 5)
    precondition(reply["version"] as? Int == 1)
    precondition(reply["kind"] as? String == "response")
    precondition(reply["topic"] as? String == "native.status")
    precondition(reply["requestId"] as? String == "status-123_A")
    precondition(payload.count == 3)
    precondition(payload["status"] as? String == "inactive")
    precondition(payload["scanVerified"] as? Bool == false)
    precondition(payload["authorizesOpen"] as? Bool == false)

    let invalid: [Any?] = [
      nil, NSNull(), "not-an-envelope", [:],
      request.merging(["version": 2]) { _, newer in newer },
      request.merging(["version": true]) { _, newer in newer },
      request.merging(["kind": "event"]) { _, newer in newer },
      request.merging(["kind": "response"]) { _, newer in newer },
      request.merging(["topic": "scan.pdf"]) { _, newer in newer },
      request.merging(["topic": "native.open"]) { _, newer in newer },
      request.merging(["requestId": "invalid/path"]) { _, newer in newer },
      request.merging(["requestId": ""]) { _, newer in newer },
      request.merging(["requestId": String(repeating: "a", count: 81)]) { _, newer in newer },
      request.merging(["payload": ["file": "/private/sample.pdf"]]) { _, newer in newer },
      request.merging(["payload": "hello"]) { _, newer in newer },
      request.merging(["extra": "unexpected"]) { _, newer in newer },
      request.filter { $0.key != "payload" }
    ]
    for (index, candidate) in invalid.enumerated() {
      precondition(SafariNativeMessagingAdapter.reply(to: candidate) == nil,
                   "Invalid native request #\(index) must be rejected")
    }
    // No state may carry from one request to the next.
    precondition(SafariNativeMessagingAdapter.reply(to: request)?["requestId"] as? String == "status-123_A")
    print("Safari native messaging adapter: valid status and \(invalid.count) rejection cases passed")
  }
}
