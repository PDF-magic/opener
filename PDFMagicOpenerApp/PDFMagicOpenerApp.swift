import AppKit
import SwiftUI

// Menu bar decision (opener-0176): do not install a persistent status item.
// This windowed preferences app does not own ongoing PDF scans or offer
// background controls; the separate PDF handler remains usable when this
// application is closed. Do not turn the app into an LSUIElement agent.
// See docs/menu-bar-decision.md for rationale and reconsideration criteria.
// Standalone preferences UI target. The existing AppKit/ClamAV scan gate
// continues to handle PDFs; this target does not register as a PDF opener.
@main
struct PDFMagicOpenerApp: App {
  var body: some Scene {
    WindowGroup("PDF Magic Opener") {
      MainPreferencesView()
    }
    .commands {
      AboutMenuCommands()

      CommandGroup(replacing: .appTermination) {
        Button("Quit PDF Magic Opener") {
          NSApplication.shared.terminate(nil)
        }
        .keyboardShortcut("q", modifiers: [.command])
      }
    }

    Window("About PDF Magic Opener", id: "about") {
      AboutView()
    }
    .windowResizability(.contentSize)

    // Use SwiftUI's managed Settings window, with the standard
    // Command-comma shortcut and the existing main preferences content.
    Settings {
      MainPreferencesView()
    }
    .keyboardShortcut(",", modifiers: .command)
  }
}

private struct AboutMenuCommands: Commands {
  @Environment(\.openWindow) private var openWindow

  var body: some Commands {
    CommandGroup(replacing: .appInfo) {
      Button("About PDF Magic Opener") {
        openWindow(id: "about")
      }
    }
  }
}

