import AppKit
import Foundation

// Read only the established scan-handler bundle ID, not unrelated PDF apps
// or the separately identified SwiftUI preferences application.
let urls = NSWorkspace.shared.urlsForApplications(
    withBundleIdentifier: "local.studio.brave-pdf-opener"
)
let paths = urls.map { $0.standardizedFileURL.path }.sorted()
do {
    let data = try JSONSerialization.data(withJSONObject: paths)
    FileHandle.standardOutput.write(data)
} catch {
    fputs("Cannot enumerate PDF opener registrations.\n", stderr)
    exit(1)
}
