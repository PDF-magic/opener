import Foundation
import UniformTypeIdentifiers

@main
struct PDFHandlerLookupTests {
    static func main() {
        var queriedTypes: [String] = []
        let registered = registeredPDFHandlerBundleIdentifier { contentType in
            queriedTypes.append(contentType)
            return "com.apple.Preview"
        }
        precondition(queriedTypes == [UTType.pdf.identifier],
                     "Only the actual PDF content type may be queried")
        precondition(registered == "com.apple.Preview",
                     "Report the registered PDF handler without substituting a browser")

        let opener = registeredPDFHandlerBundleIdentifier { _ in
            "local.studio.brave-pdf-opener"
        }
        precondition(opener == "local.studio.brave-pdf-opener",
                     "The scan gate itself may be the registered PDF handler")

        let otherReader = registeredPDFHandlerBundleIdentifier { _ in
            "com.adobe.Reader"
        }
        precondition(otherReader == "com.adobe.Reader",
                     "A non-browser PDF reader must be reported verbatim")

        precondition(registeredPDFHandlerBundleIdentifier(lookup: { _ in nil }) == nil,
                     "Absent PDF associations must fail closed")
        for invalid in ["", " ", "\n", "com.apple.Preview\n",
                        " com.apple.Preview", "com.apple.Preview\t"] {
            precondition(registeredPDFHandlerBundleIdentifier(lookup: { _ in invalid }) == nil,
                         "Invalid or multi-line handler IDs must not be reported")
        }

        print("PASS: read-only PDF handler lookup, including opener and non-browser readers.")
    }
}
