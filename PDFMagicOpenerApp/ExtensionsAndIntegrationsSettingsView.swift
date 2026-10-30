import SwiftUI

// Informational extensions and integrations page for the standalone preferences
// app. Finder actions and browser handoff belong to the installed PDF opener;
// viewing this page must not change extensions, browser selections or scan policy.
struct ExtensionsAndIntegrationsSettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Extensions and Integrations")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("How PDF Magic Opener works with macOS and other applications.")
          .foregroundStyle(.secondary)

        GroupBox("Finder integration") {
          integrationDetail(
            "Open and scan documents",
            "The existing Finder action can scan local files before opening them. It remains separate from this settings window."
          )
        }
        .accessibilityIdentifier("finderIntegrationSection")

        GroupBox("Browser and application handoff") {
          integrationDetail(
            "Verified PDF opening",
            "The installed PDF opener checks documents before handing verified PDFs to the selected application. Browser choices are managed by the existing preference tools."
          )
        }
        .accessibilityIdentifier("browserIntegrationSection")

        // No authenticated browser-to-app bridge is implemented. Do not infer
        // connection or scanner protection merely from an installed extension.
        GroupBox("Extension connection") {
          HStack(alignment: .top, spacing: 10) {
            Image(systemName: "circle.fill")
              .font(.caption)
              .foregroundStyle(.secondary)
              .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 6) {
              Text("Not connected")
                .font(.headline)
              Text("No verified browser-to-app connection is available. This status is not a malware scan result or permission to open a PDF.")
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            }
          }
          .padding(12)
          .frame(maxWidth: .infinity, alignment: .leading)
          .accessibilityElement(children: .combine)
          .accessibilityLabel("Extension connection: Not connected")
          .accessibilityIdentifier("extensionConnectionStatus")
        }
        .accessibilityIdentifier("extensionConnectionSection")

        GroupBox("Extensions") {
          integrationDetail(
            "Extension management",
            "This page does not install, enable, or disable extensions. It does not report extension availability or activation status."
          )
        }
        .accessibilityIdentifier("extensionsSection")
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("extensionsAndIntegrationsSettingsPage")
  }

  private func integrationDetail(_ title: String, _ detail: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title).font(.headline)
      Text(detail)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .padding(12)
    .frame(maxWidth: .infinity, alignment: .leading)
  }
}
