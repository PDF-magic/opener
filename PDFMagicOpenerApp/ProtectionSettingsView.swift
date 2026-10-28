import SwiftUI

// The Protection page describes current protections only. The scan gate and
// user-selected applications are owned by the separate installed PDF handler.
// Displaying this page must never make protection controls appear configurable
// before a safe, persistent settings interface is implemented.
struct ProtectionSettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Protection")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("How PDF Magic Opener checks files before opening them.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

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
