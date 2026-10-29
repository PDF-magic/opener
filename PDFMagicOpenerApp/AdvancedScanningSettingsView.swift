import SwiftUI

// Advanced Scanning is informational except for the explicitly confirmed
// optional-limit override reset. Installed scan gates remain authoritative;
// this page cannot change their fixed safety limits or the PDF application.
struct AdvancedScanningSettingsView: View {
  @State private var showRestoreRecommendedLimitsConfirmation = false
  @State private var recommendedLimitsStatus: String?

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Advanced Scanning")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Learn how the installed scanner protects documents before opening. Scanning behavior is managed by the existing PDF-opening workflow; this page does not modify it.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        // Reference values from the mandatory Built-in scan gate, not controls.
        // Present them before any advanced explanations or future controls.
        GroupBox {
          VStack(alignment: .leading, spacing: 10) {
            Text("These are the Built-in scanner defaults for reference. Viewing them does not change scanner behavior or reset saved choices.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            LabeledContent("Scanner", value: "ClamAV checks files locally before opening")
            LabeledContent("PDF scan timeout", value: "30 minutes")
            LabeledContent("Other-file scan timeout", value: "3 minutes")
            LabeledContent("Non-PDF file limit", value: "512 MB per file")
            LabeledContent("Required signatures", value: "main and daily; checked within 48 hours")

            Text("Only verified clean results can be opened. PDF scans also obey ClamAV engine limits. Advanced scanner parameters are not editable here.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        } label: {
          Label("Built-in scanner defaults", systemImage: "list.bullet.rectangle")
        }
        .accessibilityIdentifier("advancedScanningDefaultsSection")

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

        GroupBox {
          VStack(alignment: .leading, spacing: 8) {
            Label("Unusually resource-intensive settings", systemImage: "exclamationmark.triangle.fill")
              .font(.headline)
              .accessibilityAddTraits(.isHeader)

            Text("Large or complex documents, and unusually high file-size limits, archive-depth limits, or scan timeouts, can substantially increase CPU use, memory pressure, and scanning time. Review resource impact before raising any optional scanner limits if they become available.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Text("Scanner limits are currently fixed by the installed scan gate. This informational warning cannot change scanning, approve a file, bypass a failed scan, or modify your saved choices.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .padding(12)
          .frame(maxWidth: .infinity, alignment: .leading)
        } label: {
          Label("Resource usage warning", systemImage: "exclamationmark.triangle")
        }
        .accessibilityIdentifier("advancedScanningResourceWarning")

        GroupBox("Recommended scanner limits") {
          VStack(alignment: .leading, spacing: 10) {
            Text("The installed scanner currently enforces fixed safety limits. There is no editable scanner-limit control in this version.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Text("Restore Recommended Limits clears only a recognized saved optional concurrency override, if one exists. It does not change the active two-scan limit, file-size checks, your PDF application, or unrelated preferences.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Button("Restore Recommended Limits") {
              showRestoreRecommendedLimitsConfirmation = true
            }
            .accessibilityIdentifier("restoreRecommendedLimitsButton")
            .accessibilityHint("Confirm before clearing a saved optional scanner concurrency override.")

            if let recommendedLimitsStatus {
              Text(recommendedLimitsStatus)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("restoreRecommendedLimitsStatus")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("recommendedScannerLimitsSection")

        Text("Advanced scanning controls are not configurable in this version. Scanner parameters are not user-editable: fixed ClamAV options protect the scan gate. Existing scanner protections and your saved choices remain unchanged.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("advancedScanningSettingsPage")
    .confirmationDialog(
      "Restore Recommended Limits?",
      isPresented: $showRestoreRecommendedLimitsConfirmation
    ) {
      Button("Restore Recommended Limits", role: .destructive) {
        restoreRecommendedLimits()
      }
      Button("Cancel", role: .cancel) {}
    } message: {
      Text("Only the recognized optional concurrency override will be cleared, if present. Installed scanner safety limits and all other saved preferences remain unchanged.")
    }
  }

  private func restoreRecommendedLimits() {
    switch RecommendedScannerLimitsReset.restore() {
    case .restored:
      recommendedLimitsStatus = "Optional concurrency override cleared. Installed scanner limits remain unchanged."
    case .alreadyRecommended:
      recommendedLimitsStatus = "Recommended limits already apply. No saved scanner override was changed."
    case .unavailable:
      recommendedLimitsStatus = "Could not restore the optional scanner limit. Existing settings were preserved."
    }
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
