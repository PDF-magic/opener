import Foundation
import SwiftUI

@main
struct ManualUpdateActionsTests {
  static func main() {
    func verify(_ json: String, _ installed: String, _ expected: String) {
      let result = ManualUpdateActions.releaseMessage(
        data: Data(json.utf8), installedVersion: installed)
      precondition(result.contains(expected), "Unexpected result: \(result)")
    }
    verify(#"{"tag_name":"v1.1.0"}"#, "1.0", "is available")
    verify(#"{"tag_name":"1.0"}"#, "1.0.0", "No newer")
    verify(#"{"tag_name":"v0.9.0"}"#, "1.0", "No newer")
    verify(#"{"tag_name":"v1.1.0"}"#, "unknown", "cannot be compared")
    verify(#"{"tag_name":"v1.0.0-beta"}"#, "1.0", "could not be verified")
    verify(#"{"tag_name":"v999999999999.0"}"#, "1.0", "could not be verified")
    verify(#"{"unexpected":true}"#, "1.0", "could not be verified")
    print("Manual update release comparison tests passed")
  }
}
