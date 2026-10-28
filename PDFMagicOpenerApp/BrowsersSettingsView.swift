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
            "The installed browser preferences utility discovers supported applications and shows their names and versions. Refresh the inventory in that utility when browsers change.",
            helpText: "Discovery lists installed apps; being listed does not select a browser or confirm that every PDF can be displayed."
          )
        }
        .accessibilityIdentifier("installedBrowsersSection")

        GroupBox("Preferred PDF application") {
          browserSettingDetail(
            "Saved selection",
            "Your existing PDF destination remains in effect. Viewing this page does not select another browser or change the macOS default.",
            helpText: "Your preferred PDF destination is separate from the macOS default browser and the system default PDF handler."
          )
        }
        .accessibilityIdentifier("preferredBrowserSection")

        GroupBox("Additional applications") {
          browserSettingDetail(
            "Custom choices",
            "Manually added applications remain managed by the existing browser preference tools. This page does not overwrite those customizations.",
            helpText: "A custom application is a saved destination choice, not a security exception; the installed opener still verifies files before handoff."
          )
        }
        .accessibilityIdentifier("customBrowserSection")
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("browsersSettingsPage")
  }

  private func browserSettingDetail(_ title: String, _ description: String, helpText: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .font(.headline)
      Text(description)
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
