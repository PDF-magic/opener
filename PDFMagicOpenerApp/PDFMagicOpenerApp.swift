import SwiftUI

// Standalone preferences UI target. The existing AppKit/ClamAV scan gate
// continues to handle PDFs; this target does not register as a PDF opener.
@main
struct PDFMagicOpenerApp: App {
  var body: some Scene {
    WindowGroup("PDF Magic Opener") {
      MainPreferencesView()
    }

    // The standard macOS Settings command (Command-,) is always available
    // in this independent UI process, including while the PDF scan-gate app
    // is scanning. Opening Settings never touches the scanner's lifetime pipe.
    Settings {
      MainPreferencesView()
    }
  }
}

