import SwiftUI

// Advanced Scanning is a dedicated, read-only preferences destination.
// The installed ClamAV scan gate is authoritative; displaying this view
// never changes scanner configuration or the user's PDF application choice.
struct AdvancedScanningSettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Advanced Scanning")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Learn how the installed scanner protects documents before opening. Scanning behavior is managed by the existing PDF-opening workflow; this page does not modify it.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox {
          scanningDetail(
            "Local malware checks",
            "The installed workflow runs ClamAV before handing a document to the selected application. Opening this page does not start or skip a scan.",
            helpText: "Malware signatures are local definitions used by ClamAV to check files. The settings page does not inspect signature freshness."
          )
        } label: {
          Label("Malware scanning", systemImage: "checkmark.shield")
        }
        .accessibilityIdentifier("advancedScanningMalwareSection")

        GroupBox {
          scanningDetail(
            "Files awaiting download",
            "Files must be available locally before the existing workflow can scan and open them. This page does not override those readiness checks.",
            helpText: "A cloud placeholder or unfinished download may not contain readable file data yet; the installed handler waits for a locally available file."
          )
        } label: {
          Label("File readiness", systemImage: "doc.badge.clock")
        }
        .accessibilityIdentifier("advancedScanningReadinessSection")

        GroupBox {
          scanningDetail(
            "Unsuccessful scans",
            "The existing opening workflow decides whether a file can be handed off after scanning. No bypass, approval, or exception control is offered here.",
            helpText: "An inconclusive or interrupted scan is not a clean result. This page cannot approve a file or override the opening decision."
          )
        } label: {
          Label("Scan results", systemImage: "exclamationmark.shield")
        }
        .accessibilityIdentifier("advancedScanningResultsSection")

        Text("Advanced scanning controls are not configurable in this version. Scanner parameters are not user-editable: fixed ClamAV options protect the scan gate. Existing scanner protections and your saved choices remain unchanged.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("advancedScanningSettingsPage")
  }

  private func scanningDetail(_ title: String, _ detail: String, helpText: String) -> some View {
    VStack(alignment: .leading, spacing: 8) {
      Text(title)
        .font(.headline)
      Text(detail)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
      Label(helpText, systemImage: "info.circle")
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .help(helpText)
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
