import SwiftUI

// Passive UI for the future explicitly enabled optional history feature.
// The app defaults to hiding this destination. Never infer opt-in from the
// existence of stored scanner metadata or the 90-day clean-scan cache.
struct ScanHistorySettingsView: View {
  // This page stays hidden until the owning integration confirms opt-in.
  // Merely opening the gated page does not read history.
  @State private var recentScanHistory: RecentScanHistoryLoad?
  @State private var inspectedResult: RecentScanHistoryRow?
  @State private var showClearHistoryConfirmation = false
  @State private var showClearHistoryResult = false
  @State private var clearHistoryResultMessage = ""
  @State private var retentionDays = ScanHistoryRetentionStore.defaultDays
  @State private var retentionReady = false
  @State private var retentionMessage: String?

  private func expireHistory() {
    switch ScanHistoryRetentionStore.removeExpired() {
    case .removed(let count):
      retentionMessage = "Removed \(count) expired scan history entries."
    case .nothingToRemove:
      retentionMessage = nil
    case .unavailable:
      retentionMessage = "Could not safely remove expired scan history."
    }
  }

  private var retentionSelection: Binding<Int> {
    Binding(
      get: { retentionDays },
      set: { days in
        guard retentionReady else { return }
        guard ScanHistoryRetentionStore.saveDays(days) else {
          retentionMessage = "Could not safely save history retention."
          return
        }
        retentionDays = days
        inspectedResult = nil
        recentScanHistory = nil
        expireHistory()
      }
    )
  }

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
            Text("This page does not automatically display, export, or clear all saved results. Expired optional history rows are removed automatically according to the selected retention period. The owning integration must independently verify the user's opt-in before enabling this page and collecting any entries.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Picker("Keep scan history for", selection: retentionSelection) {
              ForEach(ScanHistoryRetentionStore.allowedDays, id: \.self) { days in
                Text("\(days) days").tag(days)
              }
            }
            .disabled(!retentionReady)
            .accessibilityIdentifier("scanHistoryRetentionPicker")

            if let retentionMessage {
              Text(retentionMessage)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("scanHistoryRetentionStatus")
            }

            Button("Show recent scan results") {
              inspectedResult = nil
              if case .unavailable = ScanHistoryRetentionStore.removeExpired() {
                recentScanHistory = .unavailable
              } else {
                recentScanHistory = RecentScanHistoryReader.load()
              }
            }
            .accessibilityIdentifier("showRecentScanResultsButton")
            .disabled(!retentionReady)

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

        Text("Viewing this enabled page removes expired optional history rows only. The scanner and unrelated preferences remain unchanged.")
          .font(.footnote)
          .foregroundStyle(.secondary)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("scanHistorySettingsPage")
    .task {
      guard let savedDays = ScanHistoryRetentionStore.selectedDays() else {
        retentionMessage = "History retention settings could not be read safely."
        return
      }
      retentionDays = savedDays
      expireHistory()
      retentionReady = true
    }
    .sheet(item: $inspectedResult) { row in
      ScanHistoryResultDetailView(row: row)
    }
    .confirmationDialog(
      "Permanently clear saved scan history?",
      isPresented: $showClearHistoryConfirmation,
      titleVisibility: .visible
    ) {
      Button("Clear History", role: .destructive) {
        // Discard any open detail before deleting its underlying metadata.
        inspectedResult = nil
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
