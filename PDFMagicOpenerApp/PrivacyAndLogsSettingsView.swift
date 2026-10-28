import SwiftUI

// This informational page belongs only to the standalone preferences app.
// The installed PDF handler owns scans and any operational diagnostics.
// Do not imply that log management, retention controls, or telemetry settings
// exist without first implementing and validating those capabilities.
struct PrivacyAndLogsSettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Privacy and Logs")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Understand local document processing and the availability of diagnostic logs.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox("Local document processing") {
          privacyDetail(
            "Scanning happens in the installed opener",
            "The installed PDF handler performs its malware scanning locally. Opening this preferences page does not read, upload, or scan your documents."
          )
        }
        .accessibilityIdentifier("localProcessingSection")

        GroupBox("Logs and diagnostics") {
          privacyDetail(
            "Diagnostic information",
            "Any scan and diagnostic records are handled by the existing tools and operating system. This page does not read, display, export, or clear log files."
          )
        }
        .accessibilityIdentifier("diagnosticLogsSection")

        GroupBox("Privacy and log controls") {
          privacyDetail(
            "Not configurable here",
            "Log retention, diagnostic logging, and data-clearing controls are not provided in this version. No retention duration or logging status is asserted by this page."
          )
        }
        .accessibilityIdentifier("privacyControlsSection")

        Text("Viewing this page leaves active scans, quarantine safeguards, logs, and saved application preferences unchanged.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("privacyAndLogsSettingsPage")
  }

  private func privacyDetail(_ title: String, _ description: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .font(.headline)
      Text(description)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(12)
  }
}
