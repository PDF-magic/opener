import SwiftUI

// This window describes the standalone SwiftUI app. It never opens PDFs or
// mutates the existing scanner, default handlers, or user preferences.
struct AboutView: View {
  @State private var showingLicense = false

  private var version: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
      ?? "Unavailable"
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 12) {
      Text("PDF Magic Opener")
        .font(.title)
        .fontWeight(.semibold)

      Text("Version \(version)")
        .font(.subheadline)
        .foregroundStyle(.secondary)

      Divider()

      Text("GNU Affero General Public License, Version 3 (AGPL-3.0)")
        .font(.headline)

      Text("This program comes with ABSOLUTELY NO WARRANTY.")
      Text("You may share and modify it under the GNU Affero GPL v3 terms.")

      Button("View Full License…") {
        showingLicense = true
      }
      .sheet(isPresented: $showingLicense) {
        FullLicenseView()
      }
    }
    .padding(24)
    .frame(minWidth: 480)
  }
}

private struct FullLicenseView: View {
  @Environment(\.dismiss) private var dismiss

  private var licenseText: String {
    guard let url = Bundle.main.url(forResource: "LICENSE", withExtension: nil),
          let text = try? String(contentsOf: url, encoding: .utf8) else {
      return "The bundled LICENSE file is unavailable."
    }
    return text
  }

  var body: some View {
    VStack(spacing: 12) {
      Text("GNU Affero General Public License v3")
        .font(.headline)
      ScrollView {
        Text(licenseText)
          .font(.system(.body, design: .monospaced))
          .textSelection(.enabled)
          .frame(maxWidth: .infinity, alignment: .leading)
      }
      Button("Done") { dismiss() }
        .keyboardShortcut(.defaultAction)
    }
    .padding(20)
    .frame(width: 700, height: 520)
  }
}
