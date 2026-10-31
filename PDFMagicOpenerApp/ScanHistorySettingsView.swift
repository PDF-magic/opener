import SwiftUI

// Passive UI for the future explicitly enabled optional history feature.
// The app defaults to hiding this destination. Never infer opt-in from the
// existence of stored scanner metadata or the 90-day clean-scan cache.
struct ScanHistorySettingsView: View {
  // This page stays hidden until the owning integration confirms opt-in.
  // Merely opening the gated page does not read history.
  @State private var recentScanHistory: RecentScanHistoryLoad?
  @State private var inspectedResult: RecentScanHistoryRow?

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
            Text("This page does not automatically load, export, or delete document records. The owning integration must independently verify the user's opt-in before enabling this page and collecting any entries.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Button("Show recent scan results") {
              inspectedResult = nil
              recentScanHistory = RecentScanHistoryReader.load()
            }
            .accessibilityIdentifier("showRecentScanResultsButton")

            Text("Only existing, private scan-status metadata is read on request. This history contains no filenames, document contents, URLs, or verified opening outcomes.")
              .font(.footnote)
              .foregroundStyle(.secondary)

            if let recentScanHistory {
              switch recentScanHistory {
              case .empty:
                Text("No saved scan results. Automatic history collection remains off.")
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
                      // Inspect the previously validated row without further disk reads.
                      inspectedResult = row
                    } label: {
                      VStack(alignment: .leading, spacing: 4) {
                        Text(row.statusLabel).font(.headline)
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
    .sheet(item: $inspectedResult) { row in
      ScanHistoryResultDetailView(row: row)
    }
  }
}
