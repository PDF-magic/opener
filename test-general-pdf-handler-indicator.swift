import Foundation
import UniformTypeIdentifiers

@main
struct GeneralPDFHandlerIndicatorTests {
  static func main() {
    var contentTypes: [String] = []

    let opener = readGeneralPDFHandlerStatus { contentType in
      contentTypes.append(contentType)
      return "local.studio.brave-pdf-opener"
    }
    precondition(opener == .isDefault, "Installed PDF scanning handler must show the default state")
    precondition(contentTypes == [UTType.pdf.identifier],
                 "Only the PDF content type may be queried")

    for identifier in ["com.apple.Preview", "com.adobe.Reader", "com.google.Chrome",
                       "local.studio.pdfmagicopener.swiftui"] {
      let status = readGeneralPDFHandlerStatus { _ in identifier }
      precondition(status == .other(identifier),
                   "Other applications must not be shown as the scanning handler")
      precondition(status.title == "Another application is the default PDF handler")
      precondition(status.detail.contains(identifier),
                   "A different PDF handler should be identified for troubleshooting")
    }

    for invalid in [nil, "", " ", "com..broken", "com.apple.Preview\\n",
                    " com.apple.Preview"] as [String?] {
      let status = readGeneralPDFHandlerStatus { _ in invalid }
      precondition(status == .unknown, "Unavailable or malformed associations must not show success")
    }

    var lookups = 0
    var current: String? = "com.apple.Preview"
    func lookup(_ type: String) -> String? {
      precondition(type == UTType.pdf.identifier)
      lookups += 1
      return current
    }
    precondition(readGeneralPDFHandlerStatus(lookup: lookup) == .other("com.apple.Preview"))
    current = "local.studio.brave-pdf-opener"
    precondition(readGeneralPDFHandlerStatus(lookup: lookup) == .isDefault)
    current = nil
    precondition(readGeneralPDFHandlerStatus(lookup: lookup) == .unknown)
    precondition(lookups == 3, "Each refresh must query the current association again")

    print("PASS: read-only General PDF handler status, alternate handlers, unknown and refresh")
  }
}
