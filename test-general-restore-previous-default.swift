import Foundation

// Uses in-memory handler identity and fake helper closures only; no
// runner's real PDF associations or installed history may be changed.
@main
struct RestorePreviousDefaultActionTests {
  static func main() {
    let opener = PDFDefaultApplicationAction.handlerBundleID
    var current: String? = "com.apple.Preview"
    var helperCalls = 0
    var statusReads = 0
    var result: Bool?

    func status() -> String? {
      statusReads += 1
      return current
    }

    func test(_ success: Bool, result expected: Bool, after: String?) {
      result = nil
      PDFPreviousDefaultRestoreAction.request(
        currentPDFHandler: status,
        runHelper: { completion in
          helperCalls += 1
          current = after
          completion(success)
        },
        completion: { result = $0 }
      )
      precondition(result == expected)
    }

    // A later choice (or indeterminate status) must never trigger restoration.
    test(true, result: false, after: "com.apple.Preview")
    precondition(helperCalls == 0 && statusReads == 1)
    current = nil
    test(true, result: false, after: "com.apple.Preview")
    precondition(helperCalls == 0 && statusReads == 2)

    // A failing helper, an unchanged association and an unknown final
    // association must never be reported as successful.
    current = opener
    test(false, result: false, after: "com.apple.Preview")
    precondition(helperCalls == 1 && statusReads == 3)
    current = opener
    test(true, result: false, after: opener)
    precondition(helperCalls == 2 && statusReads == 5)
    current = opener
    test(true, result: false, after: nil)
    precondition(helperCalls == 3 && statusReads == 7)

    // The installed history tool verifies the exact recorded destination.
    // Here the injected helper models that verified successful transition.
    current = opener
    test(true, result: true, after: "com.apple.Preview")
    precondition(helperCalls == 4 && statusReads == 9)

    print("PASS: restore needs current scanning handler, explicit helper and verified changed association.")
  }
}
