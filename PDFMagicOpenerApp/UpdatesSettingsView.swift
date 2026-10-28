import SwiftUI

// An informational Updates page only. It must not download or install
// software, alter ClamAV definitions, or write to user preferences.
struct UpdatesSettingsView: View {
  private var applicationVersion: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
      ?? "Unavailable"
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Updates")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Application and malware-definition update information.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox("Application updates") {
          VStack(alignment: .leading, spacing: 10) {
            // Keep the version readable if a large system text size
            // cannot fit a horizontal label/value row.
            ViewThatFits(in: .horizontal) {
              LabeledContent("Installed version", value: applicationVersion)
              VStack(alignment: .leading, spacing: 4) {
                Text("Installed version")
                  .font(.headline)
                Text(applicationVersion)
                  .fixedSize(horizontal: false, vertical: true)
              }
              .frame(maxWidth: .infinity, alignment: .leading)
            }

            Text("Checking for or installing application updates is not available from this page yet.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("applicationUpdatesSection")

        GroupBox("Malware definition updates") {
          Text("ClamAV malware definitions are maintained by the existing scanner update workflow, independently of these application preferences. This page does not check their freshness or modify them.")
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
        }
        .accessibilityIdentifier("malwareDefinitionUpdatesSection")

        Spacer(minLength: 0)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("updatesSettingsPage")
  }
}
