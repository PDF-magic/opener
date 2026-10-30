import AppKit
import Foundation
import UniformTypeIdentifiers

@main
struct MaximumSafeCopyDestinationTests {
    static func main() {
        let choice = URL(fileURLWithPath: "/tmp/" + UUID().uuidString + ".PDF")
        var presentations = 0
        let accepted = MaximumSafeCopyDestination.requestDestination { panel in
            presentations += 1
            precondition(panel.title == "Save Sanitized PDF Copy")
            precondition(panel.prompt == "Choose Destination")
            precondition(panel.nameFieldStringValue == "sanitized-copy.pdf")
            precondition(panel.allowedContentTypes == [.pdf])
            precondition(panel.canCreateDirectories)
            precondition(!panel.isExtensionHidden)
            precondition(panel.message.contains("original is not changed"))
            return (.OK, choice)
        }
        precondition(presentations == 1)
        precondition(accepted == choice.standardizedFileURL)
        precondition(!FileManager.default.fileExists(atPath: choice.path))

        // Cancel never returns a path, even when the panel has one.
        precondition(MaximumSafeCopyDestination.requestDestination {
            _ in (.cancel, choice)
        } == nil)
        precondition(MaximumSafeCopyDestination.requestDestination {
            _ in (.OK, nil)
        } == nil)
        precondition(MaximumSafeCopyDestination.selectedURL(
            response: .OK, url: URL(fileURLWithPath: "/tmp/report.txt")
        ) == nil)
        precondition(MaximumSafeCopyDestination.selectedURL(
            response: .OK, url: URL(string: "https://example.org/report.pdf")
        ) == nil)
        precondition(MaximumSafeCopyDestination.selectedURL(
            response: .cancel, url: choice
        ) == nil)
        precondition(!FileManager.default.fileExists(atPath: choice.path))
        print("Maximum permanent-destination selection: all checks passed")
    }
}
