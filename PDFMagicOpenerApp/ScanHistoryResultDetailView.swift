import SwiftUI

// Only previously validated, in-memory scan metadata can be inspected here.
// This view never reads a document or authorizes launching one.
struct ScanHistoryResultDetailView: View {
  let row: RecentScanHistoryRow
  @Environment(\.dismiss) private var dismiss

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 18) {
        Text("Scan Result Details")
          .font(.title.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Saved local scan metadata")
          .foregroundStyle(.secondary)

        GroupBox("Individual scan result") {
          VStack(alignment: .leading, spacing: 12) {
            LabeledContent("Scanned", value: row.scannedAt.formatted(date: .complete, time: .standard))
            LabeledContent("Final scan status", value: row.statusLabel)
            LabeledContent("Scanner version", value: row.scannerVersion ?? "Unknown")
            LabeledContent("Effective protection profile", value: row.profile)
            LabeledContent("File opening", value: "Not verified")
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("scanHistoryIndividualMetadata")

        Text("A saved history result never authorizes opening a document. A clean scan does not confirm that a file was opened. This view contains no document name, content, attachment, browsing history, or source URL.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        Button("Done") { dismiss() }
          .keyboardShortcut(.defaultAction)
          .accessibilityIdentifier("closeScanHistoryDetailsButton")
      }
      .padding(24)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .frame(minWidth: 440, minHeight: 330)
    .accessibilityIdentifier("scanHistoryResultDetailView")
  }
}
