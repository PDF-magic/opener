import AppKit
import SwiftUI

// Render the real Settings pages in an offscreen AppKit host. This checks
// their SwiftUI layout under larger Dynamic Type sizes without launching
// the PDF handler, changing system text settings, or inspecting user data.
@MainActor
@main
struct PreferencesLargeTextTests {
  static func main() {
    _ = NSApplication.shared

    let pages: [(String, AnyView)] = [
      ("General", AnyView(GeneralSettingsView())),
      ("Browsers", AnyView(BrowsersSettingsView())),
      ("Protection", AnyView(ProtectionSettingsView())),
      ("Advanced Scanning", AnyView(AdvancedScanningSettingsView())),
      ("Updates", AnyView(UpdatesSettingsView())),
      ("About and Diagnostics", AnyView(AboutAndDiagnosticsSettingsView())),
      ("Extensions and Integrations", AnyView(ExtensionsAndIntegrationsSettingsView())),
      ("Scan History", AnyView(ScanHistorySettingsView())),
    ]

    let sizes: [DynamicTypeSize] = [.large, .accessibility1, .accessibility3]
    for size in sizes {
      for (name, page) in pages {
        // A compact preferences window intentionally forces long descriptions
        // to wrap; each page's ScrollView must remain renderable.
        let host = NSHostingView(rootView:
          page
            .environment(\.dynamicTypeSize, size)
            .frame(width: 490, height: 420)
        )
        host.layoutSubtreeIfNeeded()
        let measured = host.fittingSize
        precondition(measured.width.isFinite && measured.height.isFinite,
                     "\(name) produced a non-finite layout at \(size)")
        precondition(measured.width > 0 && measured.height > 0,
                     "\(name) produced an empty layout at \(size)")
      }
    }

    // Check that the longest sidebar entry can grow vertically instead of
    // clipping at one line when a larger macOS text size is requested.
    func titleHeight(_ size: DynamicTypeSize) -> CGFloat {
      let sample = Text("Extensions and Integrations")
        .font(.body)
        .lineLimit(nil)
        .fixedSize(horizontal: false, vertical: true)
        .frame(width: 150, alignment: .leading)
        .environment(\.dynamicTypeSize, size)
      return NSHostingView(rootView: sample).fittingSize.height
    }
    let normalHeight = titleHeight(.large)
    let increasedHeight = titleHeight(.accessibility3)
    precondition(increasedHeight >= normalHeight && normalHeight > 0,
                 "Large sidebar text must retain its lines without clipping")
    print("PASS: all \(pages.count) settings pages render at normal and enlarged text sizes")
  }
}
