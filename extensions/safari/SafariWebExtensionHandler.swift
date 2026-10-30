import Foundation
import CoreFoundation
#if canImport(SafariServices)
import SafariServices
#endif

// Safari's native messaging entry point only translates a bounded, inert status
// request. It is not a scanner, PDF authorization, or application bridge.
enum SafariNativeMessagingAdapter {
  static func reply(to raw: Any?) -> [String: Any]? {
    guard let message = raw as? [String: Any], message.count == 5,
          Set(message.keys) == Set(["version", "kind", "topic", "requestId", "payload"]),
          let version = message["version"] as? NSNumber,
          CFGetTypeID(version) != CFBooleanGetTypeID(), version == NSNumber(value: 1),
          let kind = message["kind"] as? String, kind == "request",
          let topic = message["topic"] as? String, topic == "native.status",
          let requestId = message["requestId"] as? String,
          !requestId.isEmpty, requestId.utf8.count <= 80,
          requestId.utf8.allSatisfy({ byte in
            (byte >= 65 && byte <= 90) || (byte >= 97 && byte <= 122) ||
              (byte >= 48 && byte <= 57) || byte == 45 || byte == 95
          }),
          message["payload"] is NSNull,
          JSONSerialization.isValidJSONObject(message),
          let encoded = try? JSONSerialization.data(withJSONObject: message),
          encoded.count <= 16 * 1024 else {
      return nil
    }

    // Never echo caller-supplied payloads or infer a PDF scan result.
    return [
      "version": 1,
      "kind": "response",
      "topic": "native.status",
      "requestId": requestId,
      "payload": [
        "status": "inactive",
        "scanVerified": false,
        "authorizesOpen": false
      ]
    ]
  }
}

#if canImport(SafariServices)
final class SafariWebExtensionHandler: NSObject, NSExtensionRequestHandling {
  func beginRequest(with context: NSExtensionContext) {
    let item = context.inputItems.first as? NSExtensionItem
    let message = item?.userInfo?[SFExtensionMessageKey]
    guard let reply = SafariNativeMessagingAdapter.reply(to: message) else {
      context.completeRequest(returningItems: [], completionHandler: nil)
      return
    }
    let response = NSExtensionItem()
    response.userInfo = [SFExtensionMessageKey: reply]
    context.completeRequest(returningItems: [response], completionHandler: nil)
  }
}
#endif
