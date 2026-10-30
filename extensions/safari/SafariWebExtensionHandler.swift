import Foundation
import SafariServices

// A Safari request is never a PDF scan or permission to open a document.
// No source URL, document, message or scanner verdict crosses this boundary.
final class SafariWebExtensionHandler: NSObject, NSExtensionRequestHandling {
  func beginRequest(with context: NSExtensionContext) {
    context.completeRequest(returningItems: [], completionHandler: nil)
  }
}
