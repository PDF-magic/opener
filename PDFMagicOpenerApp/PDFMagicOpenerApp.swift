import SwiftUI

// Standalone preferences UI target. The existing AppKit/ClamAV scan gate
// continues to handle PDFs; this target does not register as a PDF opener.
@main
struct PDFMagicOpenerApp: App {
  var body: some Scene {
    WindowGroup("PDF Magic Opener") {
      MainPreferencesView()
    }

    // SwiftUI supplies the native macOS Settings menu and brings its
    // managed window forward. Use the standard Command-comma shortcut;
    // do not route a keyboard event through the PDF-opening process.
    Settings {
      MainPreferencesView()
    }
    .keyboardShortcut(",", modifiers: .command)
  }
}

