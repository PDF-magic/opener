import AppKit
import SwiftUI

// Standalone preferences UI target. The existing AppKit/ClamAV scan gate
// continues to handle PDFs; this target does not register as a PDF opener.
@main
struct PDFMagicOpenerApp: App {
  var body: some Scene {
    WindowGroup("PDF Magic Opener") {
      MainPreferencesView()
    }
    .commands {
      CommandGroup(replacing: .appTermination) {
        Button("Quit PDF Magic Opener") {
          NSApplication.shared.terminate(nil)
        }
        .keyboardShortcut("q", modifiers: [.command])
      }
    }

    // Let macOS supply its native Settings menu item and window.
    // Command-comma opens the same preferences view without touching
    // scanning, file associations, or the saved application target.
    Settings {
      MainPreferencesView()
    }
    .keyboardShortcut(",", modifiers: .command)
  }
}

