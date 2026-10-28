import SwiftUI

// Standalone preferences UI target. The existing AppKit/ClamAV scan gate
// continues to handle PDFs; this target does not register as a PDF opener.
@main
struct PDFMagicOpenerApp: App {
  var body: some Scene {
    WindowGroup("PDF Magic Opener") {
      ContentView()
    }
  }
}

private struct ContentView: View {
  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("PDF Magic Opener")
        .font(.title)
      Text("Application settings will appear here.")
        .foregroundStyle(.secondary)
    }
    .padding(24)
    .frame(minWidth: 420, minHeight: 220)
  }
}
