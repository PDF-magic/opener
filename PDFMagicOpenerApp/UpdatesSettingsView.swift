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
            LabeledContent("Installed version", value: applicationVersion)

            Text("Checking for or installing application updates is not available from this page yet.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Label("The installed version comes from this app bundle. It does not tell you whether newer software exists.", systemImage: "info.circle")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("applicationUpdatesSection")

        GroupBox("Malware definition updates") {
          VStack(alignment: .leading, spacing: 10) {
            Text("ClamAV malware definitions are maintained by the existing scanner update workflow, independently of these application preferences. This page does not check their freshness or modify them.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Label("Malware definitions describe threats recognized by the scanner. Their update schedule is separate from app updates, and this page cannot confirm when they were last refreshed.", systemImage: "info.circle")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
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
