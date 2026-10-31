import SwiftUI

// Passive UI for the future explicitly enabled optional history feature.
// The app defaults to hiding this destination. Never infer opt-in from the
// existence of stored scanner metadata or the 90-day clean-scan cache.
struct ScanHistorySettingsView: View {
  // This page stays hidden until the owning integration confirms opt-in.
  // Merely opening the gated page does not read history.
  @State private var recentScanHistory: RecentScanHistoryLoad?
  @State private var showClearHistoryConfirmation = false
  @State private var showClearHistoryResult = false
  @State private var clearHistoryResultMessage = ""

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
              recentScanHistory = RecentScanHistoryReader.load()
            }
            .accessibilityIdentifier("showRecentScanResultsButton")

            Button("Clear History…", role: .destructive) {
              showClearHistoryConfirmation = true
            }
            .accessibilityIdentifier("clearScanHistoryButton")
            .help("Delete only saved optional scan-history metadata")

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
                    VStack(alignment: .leading, spacing: 4) {
                      Text(row.statusLabel).font(.headline)
                      Text(row.scannedAt.formatted(date: .abbreviated, time: .shortened))
                      Text("Scanner: \(row.scannerVersion ?? "Unknown") · Profile: \(row.profile)")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityElement(children: .combine)
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
    .confirmationDialog(
      "Permanently clear saved scan history?",
      isPresented: $showClearHistoryConfirmation,
      titleVisibility: .visible
    ) {
      Button("Clear History", role: .destructive) {
        switch ClearScanHistoryStore.clear() {
        case .cleared:
          recentScanHistory = .empty
          clearHistoryResultMessage = "Saved scan history was cleared."
        case .nothingToClear:
          recentScanHistory = .empty
          clearHistoryResultMessage = "There is no saved scan history to clear."
        case .unavailable:
          recentScanHistory = .unavailable
          clearHistoryResultMessage = "History could not be cleared safely. No other application data was changed."
        }
        showClearHistoryResult = true
      }
      Button("Cancel", role: .cancel) {}
    } message: {
      Text("Delete saved optional scan-history metadata from this Mac? This cannot be undone. Scanner protections, preferences, and the clean-scan cache are not changed.")
    }
    .alert("Clear History", isPresented: $showClearHistoryResult) {
      Button("OK", role: .cancel) {}
    } message: {
      Text(clearHistoryResultMessage)
    }
  }
}
