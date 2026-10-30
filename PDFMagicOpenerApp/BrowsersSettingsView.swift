import SwiftUI

// Dedicated Browsers page for the standalone preferences app.
// Browser discovery, selection and PDF launch remain in the installed tools;
// displaying this page must not mutate user choices or scanning policy.
struct BrowsersSettingsView: View {
  @State private var scanOtherSupportedFiles = false
  @State private var scanOtherFilesStatus: String?

  private func loadOtherFilePreference() {
    scanOtherSupportedFiles = ScanOtherSupportedFilesPreference.isEnabled()
  }

  private func updateOtherFilePreference(_ enabled: Bool) {
    if ScanOtherSupportedFilesPreference.save(enabled) {
      scanOtherSupportedFiles = enabled
      scanOtherFilesStatus = "Download scan scope preference saved."
    } else {
      scanOtherSupportedFiles = ScanOtherSupportedFilesPreference.isEnabled()
      scanOtherFilesStatus = "Could not save this preference. Your previous choice is unchanged."
    }
  }

  @State private var showOnlyWarnings = false
  @State private var warningPreferenceStatus: String?

  private func updateShowOnlyWarnings(_ enabled: Bool) {
    if DownloadWarningOnlyPreference.save(enabled) {
      showOnlyWarnings = enabled
      warningPreferenceStatus = "Warning display preference saved."
    } else {
      // On persistence failure, display the confirmed effective value.
      showOnlyWarnings = DownloadWarningOnlyPreference.isEnabled()
      warningPreferenceStatus = "Could not save the warning preference. Your previous choice is unchanged."
    }
  }

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

        GroupBox("Download scanning") {
          VStack(alignment: .leading, spacing: 10) {
            Toggle("Scan Other Supported Files", isOn: Binding(
              get: { scanOtherSupportedFiles },
              set: { updateOtherFilePreference($0) }
            ))
            .accessibilityIdentifier("scanOtherSupportedFilesToggle")

            Text("Opt in to including non-PDF files supported by the native scanner if a verified browser download integration becomes available. This does not enable download monitoring, request browser permissions, change PDF scanning, or bypass safety checks. Non-PDF browser download scanning is not currently connected.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            if let scanOtherFilesStatus {
              Text(scanOtherFilesStatus)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("scanOtherSupportedFilesStatus")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("downloadScanningSettingsSection")
        .onAppear(perform: loadOtherFilePreference)

        GroupBox("Additional applications") {
          browserSettingDetail(
            "Custom choices",
            "Manually added applications remain managed by the existing browser preference tools. This page does not overwrite those customizations.",
            helpText: "A custom application is a saved destination choice, not a security exception; the installed opener still verifies files before handoff."
          )
        }
        .accessibilityIdentifier("customBrowserSection")

        GroupBox("Download warning display") {
          VStack(alignment: .leading, spacing: 10) {
            Toggle("Show Only Warnings", isOn: Binding(
              get: { showOnlyWarnings },
              set: { updateShowOnlyWarnings($0) }
            ))
            .accessibilityIdentifier("showOnlyDownloadWarningsToggle")

            Text("When verified download-scan results become available, hide optional clean and informational summaries. Malware detections, scan failures, incomplete checks, blocked results, and other security warnings must always remain visible. This does not activate browser scanning or change the Show Scan Results preference.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            if let warningPreferenceStatus {
              Text(warningPreferenceStatus)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("showOnlyDownloadWarningsStatus")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("downloadWarningDisplaySection")
        .onAppear {
          // Display-only: never request downloads permission or start scanning.
          showOnlyWarnings = DownloadWarningOnlyPreference.isEnabled()
        }
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
