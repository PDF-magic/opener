import SwiftUI

// Read-only diagnostic information about the standalone preferences app.
// The installed PDF handler and ClamAV scanning process are separate;
// this page never reads logs, probes documents, or changes protection settings.
struct AboutAndDiagnosticsSettingsView: View {
  private var appVersion: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
      ?? "Unavailable"
  }

  private var appBuild: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String
      ?? "Unavailable"
  }

  private var bundleIdentifier: String {
    Bundle.main.bundleIdentifier ?? "Unavailable"
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("About and Diagnostics")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Information about the running preferences application and the separate PDF-opening workflow.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox("Application") {
          VStack(alignment: .leading, spacing: 12) {
            diagnosticDetail("PDF Magic Opener", "Version \(appVersion) · Build \(appBuild)")
            diagnosticDetail("Bundle identifier", bundleIdentifier)
            Text("License: GNU Affero General Public License v3. Open About PDF Magic Opener from the application menu to view the complete bundled license.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(12)
        }
        .accessibilityIdentifier("aboutDiagnosticsApplicationSection")

        GroupBox("Environment") {
          diagnosticDetail(
            "macOS",
            ProcessInfo.processInfo.operatingSystemVersionString
          )
          .padding(12)
          .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityIdentifier("aboutDiagnosticsEnvironmentSection")

        GroupBox("Scanning diagnostics") {
          VStack(alignment: .leading, spacing: 12) {
            diagnosticDetail(
              "Independent scan handler",
              "PDF scanning and document handoff are performed by the separately installed native handler, not by this preferences app."
            )
            diagnosticDetail(
              "Verification status",
              "Scanner availability, malware definitions, and recent scan results are not checked by this page. No successful scan is implied."
            )
            diagnosticDetail(
              "Privacy",
              "This page does not read, collect, or export scan logs, document paths, or stored browser choices."
            )
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(12)
        }
        .accessibilityIdentifier("aboutDiagnosticsScannerSection")
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("aboutAndDiagnosticsSettingsPage")
  }

  private func diagnosticDetail(_ title: String, _ detail: String) -> some View {
    VStack(alignment: .leading, spacing: 5) {
      Text(title)
        .font(.headline)
      Text(detail)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .textSelection(.enabled)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
