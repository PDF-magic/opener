import Foundation

@main
struct DetectPDFHandlerChangeTests {
    static func main() {
        var current: String? = "local.studio.brave-pdf-opener"
        var lookups = 0
        func lookup() -> String? {
            lookups += 1
            return current
        }

        // Launch Services may change between checks, without any opener action.
        precondition(detectPDFHandlerChange(lookup: lookup) == .unchanged)
        current = "com.apple.Preview"
        precondition(detectPDFHandlerChange(lookup: lookup) == .replaced("com.apple.Preview"),
                     "Preview becoming default must be detected")
        current = "com.adobe.Reader"
        precondition(detectPDFHandlerChange(lookup: lookup) == .replaced("com.adobe.Reader"),
                     "A non-browser PDF reader must be detected without substitution")
        current = "local.studio.brave-pdf-opener"
        precondition(detectPDFHandlerChange(lookup: lookup) == .unchanged,
                     "Restoring the opener must clear the changed state")
        current = nil
        precondition(detectPDFHandlerChange(lookup: lookup) == .unknown,
                     "An unavailable registration must never be mistaken for another app")
        precondition(lookups == 5, "Each check must query the current association anew")

        precondition(detectPDFHandlerChange(
            expectedBundleIdentifier: "com.example.CustomPDFGate",
            lookup: { "com.example.CustomPDFGate" }) == .unchanged,
            "Ownership comparisons must use the supplied expected identity")
        precondition(detectPDFHandlerChange(
            expectedBundleIdentifier: "com.example.CustomPDFGate",
            lookup: { "com.apple.Preview" }) == .replaced("com.apple.Preview"))

        print("PASS: read-only PDF handler takeover detection and recovery")
    }
}
