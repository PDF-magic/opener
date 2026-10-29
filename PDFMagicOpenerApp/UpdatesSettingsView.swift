import SwiftUI

// An informational Updates page only. It must not download or install
// software, alter ClamAV definitions, or write to user preferences.
struct UpdatesSettingsView: View {

  // A read-only snapshot taken when the Updates pane is constructed.
  // Times are displayed in the user's local time zone; "Unavailable" is
  // intentional for older installations or invalid/unreadable markers.
  private func timestampRow(_ label: String, _ date: Date?) -> some View {
    let value = date.map { $0.formatted(date: .abbreviated, time: .standard) }
      ?? "Unavailable"
    return ViewThatFits(in: .horizontal) {
      LabeledContent(label, value: value)
      VStack(alignment: .leading, spacing: 4) {
        Text(label).font(.headline)
        Text(value).fixedSize(horizontal: false, vertical: true)
      }
    }
  }

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
            // Permit a stacked label/value when system text cannot fit
            // the default horizontal presentation.
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
          TimelineView(.periodic(from: .now, by: 2)) { timeline in
            let signatureStatus = SignatureUpdateStatus.readInstalled()
            VStack(alignment: .leading, spacing: 10) {
              if let active = SignatureUpdateProgress.readInstalled(now: timeline.date) {
                HStack(alignment: .center, spacing: 12) {
                  ProgressView()
                    .progressViewStyle(.circular)
                    .accessibilityHidden(true)
                  VStack(alignment: .leading, spacing: 4) {
                    Text("Signature update in progress")
                      .font(.headline)
                    Text("Checking and downloading ClamAV definitions…")
                      .foregroundStyle(.secondary)
                    Text("Started at " + active.startedAt.formatted(date: .abbreviated, time: .standard))
                      .font(.footnote)
                      .foregroundStyle(.secondary)
                  }
                  .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("signatureUpdateProgress")
              } else {
                Text("No active signature update detected.")
                  .foregroundStyle(.secondary)
                  .accessibilityIdentifier("signatureUpdateIdle")
              }
            Text(signatureStatus.message)
              .font(.headline)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("signatureUpdateSummary")
            timestampRow("Last attempted update", signatureStatus.lastAttempt)
              .accessibilityIdentifier("signatureUpdateLastAttempt")
            timestampRow("Last successful update", signatureStatus.lastSuccess)
              .accessibilityIdentifier("signatureUpdateLastSuccess")
            Text("Times are shown in your local time zone.")
              .font(.footnote)
              .foregroundStyle(.secondary)
            Text("ClamAV definitions are maintained by the existing scanner update workflow independently of these preferences. These timestamps do not verify signature freshness or database health.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Label("Malware definitions describe threats recognized by the scanner. Their update schedule is separate from app updates. An attempted update is not proof of success. The installed scanner still checks signature freshness and database validity before scanning; viewing this page never starts an update.", systemImage: "info.circle")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
          }
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
