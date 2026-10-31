import SwiftUI

// Passive UI for the future explicitly enabled optional history feature.
// The app defaults to hiding this destination. Never infer opt-in from the
// existence of stored scanner metadata or the 90-day clean-scan cache.
struct ScanHistorySettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Scan History")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Review the boundaries of optional local scan history.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox("History availability") {
          VStack(alignment: .leading, spacing: 8) {
            Text("The Scan History page is available only after the owning feature explicitly enables it.")
            Text("This page does not load, list, export, or delete document records. A future history integration must independently verify the user's opt-in before collecting or displaying any entries.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("scanHistoryAvailabilitySection")

        GroupBox("Privacy and protection") {
          Text("History is not an authorization to open a document. The separate scanner still enforces malware checks, file integrity, signature freshness, and quarantine. Optional history must not contain PDF bytes, document text, attachments, browsing history, or source URLs.")
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
        }
        .accessibilityIdentifier("scanHistoryPrivacySection")

        Text("Viewing this page does not change scan history, saved preferences, or the existing scanner.")
          .font(.footnote)
          .foregroundStyle(.secondary)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("scanHistorySettingsPage")
  }
}
