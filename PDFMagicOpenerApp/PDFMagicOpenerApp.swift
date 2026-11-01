import AppKit
import SwiftUI
#if DEBUG
import Darwin
#endif

// Menu bar decision (opener-0176): do not install a persistent status item.
// This windowed preferences app does not own ongoing PDF scans or offer
// background controls; the separate PDF handler remains usable when this
// application is closed. Do not turn the app into an LSUIElement agent.
// See docs/menu-bar-decision.md for rationale and reconsideration criteria.
// Launch-at-login decision (opener-0199): no automatic startup is needed.
// This windowed preferences app does not own scan requests or long-running
// work. The installed PDF opener handles open events independently; the
// separate malware-signature update LaunchAgent is not a preferences login
// item. See docs/launch-at-login-decision.md.
// Standalone preferences UI target. The existing AppKit/ClamAV scan gate
// continues to handle PDFs; this target does not register as a PDF opener.
@main
struct PDFMagicOpenerApp: App {
  init() {
    // Materialize defaults before either preferences window is shown.
    InitialConfiguration.createIfNeeded()
  }

  var body: some Scene {
    WindowGroup("PDF Magic Opener") {
      FirstRunWelcomeGate {
        MainPreferencesView()
      }
        .onOpenURL { url in
          // Only raise the existing preferences window. Never scan or open URL data.
          guard url.absoluteString == "pdfmagicopener://preferences" else { return }
          NSApplication.shared.activate(ignoringOtherApps: true)
        }
        .onAppear {
#if DEBUG
          LaunchBenchmarkMarker.markFirstViewAppearance()
#endif
        }
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

#if DEBUG
private enum LaunchBenchmarkMarker {
  private static var emitted = false

  static func markFirstViewAppearance() {
    guard !emitted else { return }
    emitted = true
    // Only a specifically opted-in Debug run can receive the one-byte marker.
    guard let raw = ProcessInfo.processInfo.environment["PDFMAGIC_LAUNCH_BENCHMARK_FD"],
          let fd = Int32(raw), fd >= 3 && fd <= 1024 else { return }
    var marker: UInt8 = 49 // ASCII "1"; no paths, preferences or document content.
    _ = withUnsafePointer(to: &marker) { Darwin.write(fd, $0, 1) }
  }
}
#endif

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

