import SwiftUI

// The installed ClamAV gate owns the effective protection policy. These
// planned tier cards can be selected for comparison only; they deliberately
// never persist a selection or imply an unavailable tier is enforcing scans.
private enum PlannedProtectionTier: String, CaseIterable, Identifiable {
  case standard
  case enhanced
  case maximum

  var id: String { rawValue }

  var title: String {
    switch self {
    case .standard: return "Standard"
    case .enhanced: return "Enhanced"
    case .maximum: return "Maximum"
    }
  }

  var summary: String {
    switch self {
    case .standard:
      return "Baseline ClamAV, signature freshness and verified handoff."
    case .enhanced:
      return "Planned additional inspection for PDF structures and active content."
    case .maximum:
      return "Planned isolated analysis and sanitized-copy protections."
    }
  }

  var detail: String {
    switch self {
    case .standard:
      return "Standard is a planned named tier. Existing Built-in scanning remains the active, mandatory policy."
    case .enhanced:
      return "Enhanced is not available for enforcement. Its additional inspection stages must be fully integrated and verified before activation."
    case .maximum:
      return "Maximum is not available for enforcement. Its isolated analysis, rasterization and safe-copy safeguards are still being integrated."
    }
  }
}

struct ProtectionSettingsView: View {
  @State private var selectedPreview: PlannedProtectionTier?

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Protection")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("How PDF Magic Opener checks files before opening them.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        Text("Active protection: Built-in ClamAV scanning and fail-closed opening.")
          .font(.headline)
          .fixedSize(horizontal: false, vertical: true)
          .accessibilityIdentifier("activeBuiltInProtection")

        GroupBox("Planned protection levels") {
          VStack(alignment: .leading, spacing: 12) {
            Text("Choose a card to preview its protections. All three are planned; choosing a card does not enable it, save a preference or change the scanner.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            ForEach(PlannedProtectionTier.allCases) { tier in
              Button {
                // This is a UI-only preview; scanner policy is unchanged.
                selectedPreview = tier
              } label: {
                HStack(alignment: .top, spacing: 12) {
                  Image(systemName: selectedPreview == tier
                        ? "largecircle.fill.circle" : "circle")
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)

                  VStack(alignment: .leading, spacing: 6) {
                    Text(tier.title)
                      .font(.headline)
                    Text(tier.summary)
                      .foregroundStyle(.secondary)
                      .fixedSize(horizontal: false, vertical: true)
                    Text("Preview only · Not available as an active policy")
                      .font(.footnote)
                      .foregroundStyle(.secondary)
                      .fixedSize(horizontal: false, vertical: true)
                  }
                  Spacer(minLength: 0)
                }
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color(nsColor: .controlBackgroundColor),
                            in: RoundedRectangle(cornerRadius: 10))
                .overlay {
                  RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(
                      selectedPreview == tier
                        ? Color.accentColor : Color.secondary.opacity(0.35),
                      lineWidth: selectedPreview == tier ? 2 : 1
                    )
                }
              }
              .buttonStyle(.plain)
              .accessibilityIdentifier("protectionCard-\\(tier.rawValue)")
              .accessibilityLabel("\\(tier.title) protection preview")
              .accessibilityValue(selectedPreview == tier
                                  ? "Selected for preview, not active"
                                  : "Not selected, not active")
              .accessibilityHint("Show \\(tier.title) details. This does not change scanning.")
            }

            if let selectedPreview {
              VStack(alignment: .leading, spacing: 6) {
                Text("Previewing \\(selectedPreview.title)")
                  .font(.headline)
                Text(selectedPreview.detail)
                  .foregroundStyle(.secondary)
                  .fixedSize(horizontal: false, vertical: true)
              }
              .padding(12)
              .frame(maxWidth: .infinity, alignment: .leading)
              .accessibilityIdentifier("protectionCardPreviewDetail")
            }
          }
        }
        .accessibilityIdentifier("plannedProtectionCardsSection")

        GroupBox("Malware scanning") {
          protectionDetail(
            "ClamAV scanning",
            "The installed PDF handler scans documents locally before allowing them to open. A failed or incomplete scan does not approve a document.",
            helpText: "ClamAV is a local malware scanner. This description does not run a scan or verify that a specific file is safe."
          )
        }
        .accessibilityIdentifier("malwareScanningSection")

        GroupBox("Unsafe or unverified files") {
          protectionDetail(
            "Fail-closed protection",
            "Cancelled, infected, or unverified files are not handed to a destination application. The established quarantine safeguards remain in place.",
            helpText: "Fail-closed means an interrupted, unsuccessful, or inconclusive scan does not count as permission to open the file."
          )
        }
        .accessibilityIdentifier("unsafeFilesSection")

        GroupBox("Verified application handoff") {
          protectionDetail(
            "After a clean scan",
            "The installed opener verifies the selected PDF application before handoff. Viewing this page cannot change the chosen app or bypass its checks.",
            helpText: "Handoff is the step that opens a verified file in your chosen PDF app; it is different from changing macOS default application settings."
          )
        }
        .accessibilityIdentifier("verifiedHandoffSection")

        Text("These protections are managed by the installed PDF opener. This page is informational and does not change scan settings.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("protectionSettingsPage")
  }

  private func protectionDetail(_ title: String, _ explanation: String, helpText: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .font(.headline)
      Text(explanation)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
      Label(helpText, systemImage: "info.circle")
        .font(.footnote)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
        .help(helpText)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(12)
  }
}
