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
  }
}

