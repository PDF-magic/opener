import SwiftUI

// Informational until the app has a supported notification delivery and
// preference-storage workflow. The installed PDF scan helper remains separate.
struct NotificationsSettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Notifications")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Understand how PDF Magic Opener communicates scan activity and where future notification controls will appear.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox("Scan progress") {
          notificationDetail(
            "On-screen progress",
            "When you open a PDF, the installed scan helper shows a progress window with a Cancel button while it checks the document."
          )
        }
        .accessibilityIdentifier("scanProgressNotificationsSection")

        GroupBox("Scan results") {
          notificationDetail(
            "Safe document handling",
            "The installed opener makes its own scan and handoff decisions. This preferences page does not send notifications, launch files, or change what happens after a scan."
          )
        }
        .accessibilityIdentifier("scanResultNotificationsSection")

        GroupBox("System notifications") {
          notificationDetail(
            "Not configured yet",
            "macOS notification alerts and notification preferences are not currently configured in this app. No notification permission is requested when you view this page."
          )
        }
        .accessibilityIdentifier("systemNotificationsSection")

        Text("This page is informational. Notification delivery options will require a separate implementation; existing scanner safeguards and your saved preferences remain unchanged.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("notificationsSettingsPage")
  }

  private func notificationDetail(_ title: String, _ detail: String) -> some View {
    VStack(alignment: .leading, spacing: 6) {
      Text(title)
        .font(.headline)
      Text(detail)
        .foregroundStyle(.secondary)
        .fixedSize(horizontal: false, vertical: true)
    }
    .frame(maxWidth: .infinity, alignment: .leading)
    .padding(12)
  }
}
