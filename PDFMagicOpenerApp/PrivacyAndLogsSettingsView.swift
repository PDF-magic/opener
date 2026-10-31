import SwiftUI

// This informational page belongs only to the standalone preferences app.
// The installed PDF handler owns scans and any operational diagnostics.
// Do not imply that log management, retention controls, or telemetry settings
// exist without first implementing and validating those capabilities.
struct PrivacyAndLogsSettingsView: View {
  // User action only. Merely opening this page never reads the history store.
  @State private var recentScanHistory: RecentScanHistoryLoad?
  @State private var inspectedResult: RecentScanHistoryRow?

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

        GroupBox("Optional local scan history") {
          VStack(alignment: .leading, spacing: 12) {
            privacyDetail(
              "Off by default",
              "Optional, user-visible scan history is off by default. Automatic recording is not implemented in this version. No scan-history opt-in control or store is provided here. Existing operational scan records and the clean-scan cache are separate and unchanged."
            )

            Button("Show recent scan results") {
              inspectedResult = nil
              recentScanHistory = RecentScanHistoryReader.load()
            }
            .accessibilityIdentifier("showRecentScanResultsButton")

            Text("Only existing, private scan-status metadata is read on request. No document names, contents, URLs, or confirmed file-opening outcomes are available in this history.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            if let recentScanHistory {
              switch recentScanHistory {
              case .empty:
                Text("No saved scan results. Automatic history collection is off.")
                  .foregroundStyle(.secondary)
                  .accessibilityIdentifier("recentScanHistoryEmptyState")
              case .unavailable:
                Text("Recent scan results could not be read safely.")
                  .foregroundStyle(.secondary)
                  .accessibilityIdentifier("recentScanHistoryUnavailableState")
              case .entries(let rows):
                VStack(alignment: .leading, spacing: 12) {
                  ForEach(rows) { row in
                    Button {
                      // Inspect only the already verified in-memory result.
                      inspectedResult = row
                    } label: {
                      VStack(alignment: .leading, spacing: 4) {
                        Text(row.statusLabel)
                          .font(.headline)
                        Text(row.scannedAt.formatted(date: .abbreviated, time: .shortened))
                        Text("Scanner: \(row.scannerVersion ?? "Unknown") · Profile: \(row.profile)")
                          .font(.footnote)
                          .foregroundStyle(.secondary)
                      }
                      .frame(maxWidth: .infinity, alignment: .leading)
                      .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel("Inspect \(row.statusLabel) result")
                    .accessibilityHint("Show saved metadata for this individual scan result")
                    .accessibilityIdentifier("inspectScanHistoryResult-\(row.id)")
                  }
                }
                .accessibilityIdentifier("recentScanHistoryResults")
              }
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("optionalScanHistorySection")

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
    .sheet(item: $inspectedResult) { row in
      ScanHistoryResultDetailView(row: row)
    }
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
