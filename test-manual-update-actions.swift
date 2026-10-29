import Foundation
import SwiftUI

@main
struct ManualUpdateActionsTests {
  static func main() {
    func check(_ text: String, _ main: Int, _ daily: Int) {
      guard let revisions = ManualUpdateActions.publishedRevisions(from: text) else {
        preconditionFailure("Valid published revisions rejected")
      }
      precondition(revisions.main == main && revisions.daily == daily)
    }
    check("\"1.5.4:63:28166:1700000000:0:63:49191:333\"\n", 63, 28166)
    check("1.4.3:62:28000:1700000000", 62, 28000)
    for invalid in ["", "\"oops\"", "\"1.5:0:28166\"", "\"1.5:63:-1\"",
                    "\"1.5:63:28166\"\n\"1.5:63:28167\""] {
      precondition(ManualUpdateActions.publishedRevisions(from: invalid) == nil)
    }
    func header(_ version: Int) -> Data {
      Data(("ClamAV-VDB:build-time:\(version):100:25:abcdef:signature:builder:" +
            String(repeating: " ", count: 440)).utf8)
    }
    precondition(ManualUpdateActions.databaseRevision(header: header(28166)) == 28166)
    precondition(ManualUpdateActions.databaseRevision(header: Data("garbage".utf8)) == nil)
    print("Read-only ClamAV signature revision fixture tests passed")
  }
}
