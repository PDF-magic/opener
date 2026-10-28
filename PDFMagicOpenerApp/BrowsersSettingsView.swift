import SwiftUI

// Dedicated Browsers page for the standalone preferences app.
// Browser discovery, selection and PDF launch remain in the installed tools;
// displaying this page must not mutate user choices or scanning policy.
struct BrowsersSettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Browsers")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Browser settings for verified PDF opening.")
          .foregroundStyle(.secondary)

        GroupBox("Installed browsers") {
          browserSettingDetail(
            "Browser discovery",
            "The installed browser preferences utility discovers supported applications and shows their names and versions. Refresh the inventory in that utility when browsers change."
          )
        }
        .accessibilityIdentifier("installedBrowsersSection")

        GroupBox("Preferred PDF application") {
          browserSettingDetail(
            "Saved selection",
            "Your existing PDF destination remains in effect. Viewing this page does not select another browser or change the macOS default."
          )
        }
        .accessibilityIdentifier("preferredBrowserSection")

        GroupBox("Additional applications") {
          browserSettingDetail(
            "Custom choices",
            "Manually added applications remain managed by the existing browser preference tools. This page does not overwrite those customizations."
          )
        }
        .accessibilityIdentifier("customBrowserSection")
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("browsersSettingsPage")
  }

  private func browserSettingDetail(_ title: String, _ description: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .font(.headline)
      Text(description)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(12)
  }
}
