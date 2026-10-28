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
      AboutMenuCommands()
    }

    Window("About PDF Magic Opener", id: "about") {
      AboutView()
    }
    .windowResizability(.contentSize)
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
