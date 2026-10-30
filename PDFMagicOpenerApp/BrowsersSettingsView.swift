import SwiftUI

// Dedicated Browsers page for the standalone preferences app.
// Browser discovery, selection and PDF launch remain in the installed tools;
// displaying this page must not mutate user choices or scanning policy.
struct BrowsersSettingsView: View {
  @State private var downloadMonitoringEnabled = false
  @State private var downloadMonitoringMessage: String?

  private func setDownloadMonitoring(_ enabled: Bool) {
    if BrowserDownloadMonitoringPreference.save(enabled) {
      downloadMonitoringEnabled = enabled
      downloadMonitoringMessage = "Preference saved. Browser download monitoring is not active."
    } else {
      downloadMonitoringEnabled = BrowserDownloadMonitoringPreference.isEnabled()
      downloadMonitoringMessage = "Could not save the preference. The previous setting is unchanged."
    }
  }

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

  @State private var showScanResults = true
  @State private var showScanResultsStatus: String?

  private func updateShowScanResults(_ enabled: Bool) {
    if DownloadScanResultsPreference.save(enabled) {
      showScanResults = enabled
      showScanResultsStatus = "Scan result display preference saved."
    } else {
      showScanResults = DownloadScanResultsPreference.isEnabled()
      showScanResultsStatus = "Could not save the display preference. Your previous choice is unchanged."
    }
  }

  @State private var notifyOnFailedScan = false
  @State private var failedScanNotificationStatus: String?

  private func updateNotifyOnFailedScan(_ enabled: Bool) {
    if DownloadFailedScanNotificationPreference.save(enabled) {
      notifyOnFailedScan = enabled
      failedScanNotificationStatus = "Failed-scan notification preference saved."
    } else {
      notifyOnFailedScan = DownloadFailedScanNotificationPreference.isEnabled()
      failedScanNotificationStatus = "Could not save this preference. Your previous choice is unchanged."
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

        GroupBox("Download scan results") {
          VStack(alignment: .leading, spacing: 10) {
            Toggle("Show Scan Results", isOn: Binding(
              get: { showScanResults },
              set: { updateShowScanResults($0) }
            ))
            .accessibilityIdentifier("showDownloadScanResultsToggle")

            Text("Choose whether to show optional summaries of browser download scans when a verified integration becomes available. Browser download scanning is not currently active. Blocking decisions, malware warnings, failed-scan alerts and native scanner safeguards are never disabled or hidden by this setting.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            if let showScanResultsStatus {
              Text(showScanResultsStatus)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("showDownloadScanResultsStatus")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("downloadScanResultsSection")
        .onAppear {
          // Display-only preference: never request downloads permission here.
          showScanResults = DownloadScanResultsPreference.isEnabled()
        }

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

        GroupBox("Connection health") {
          VStack(alignment: .leading, spacing: 8) {
            Label(
              BrowserNativeConnectionHealth.current.statusLabel,
              systemImage: "bolt.slash"
            )
            .font(.headline)
            .accessibilityIdentifier("browserNativeConnectionHealthIndicator")

            Text(BrowserNativeConnectionHealth.current.detail)
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("browserNativeConnectionHealthDetail")

            Text("A saved monitoring preference, installed browser or native host, and a transport-only handshake do not establish a working scan connection. No permission is requested or scan started by this indicator.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("browserNativeConnectionHealthSection")

        GroupBox("Browser downloads") {
          VStack(alignment: .leading, spacing: 8) {
            Toggle("Enable Browser Download Monitoring", isOn: Binding(
              get: { downloadMonitoringEnabled },
              set: { setDownloadMonitoring($0) }
            ))
            .accessibilityIdentifier("enableBrowserDownloadMonitoringToggle")

            Text("This saves your opt-in preference only. Browser download monitoring is not active: the browser extension is not connected to a verified scanner and cannot monitor downloads yet. Browser permissions must be granted separately.")
              .font(.subheadline)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            if let downloadMonitoringMessage {
              Text(downloadMonitoringMessage)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("browserDownloadMonitoringStatus")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("browserDownloadsSection")

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
        GroupBox("Download failure notifications") {
          VStack(alignment: .leading, spacing: 10) {
            Toggle("Notify on Failed Scan", isOn: Binding(
              get: { notifyOnFailedScan },
              set: { updateNotifyOnFailedScan($0) }
            ))
            .accessibilityIdentifier("notifyOnFailedDownloadScanToggle")

            Text("Opt in to an additional notification when an independently verified browser download scan fails or cannot finish. Required failure messages, blocked-opening alerts and security warnings remain visible regardless of this setting. Download scan notifications are not active until a separately authenticated native integration is available.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            if let failedScanNotificationStatus {
              Text(failedScanNotificationStatus)
                .foregroundStyle(.secondary)
                .accessibilityIdentifier("notifyOnFailedDownloadScanStatus")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("downloadFailureNotificationsSection")
        .onAppear {
          // Read-only load: requesting notification permission is a separate task.
          notifyOnFailedScan = DownloadFailedScanNotificationPreference.isEnabled()
        }

      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("browsersSettingsPage")
    .onAppear {
      // Reading is side-effect free; do not prompt for browser permissions.
      downloadMonitoringEnabled = BrowserDownloadMonitoringPreference.isEnabled()
    }
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
