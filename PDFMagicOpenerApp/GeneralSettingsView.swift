import SwiftUI

// General preferences are informational until configuration workflows are
// implemented. Never mutate the active PDF handler, saved browser, or scanner.
struct GeneralSettingsView: View {
  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("General")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("An overview of how PDF Magic Opener handles documents. This page does not change your settings.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox {
          VStack(alignment: .leading, spacing: 12) {
            Label("Scan before opening", systemImage: "checkmark.shield")
              .font(.headline)
            Text("The installed PDF handler checks documents with ClamAV before opening them in your selected application.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        } label: {
          Label("Document handling", systemImage: "doc.text")
        }

        GroupBox {
          VStack(alignment: .leading, spacing: 12) {
            Label("Saved application choices", systemImage: "app.badge")
              .font(.headline)
            Text("Your selected browser, default PDF handler, and existing application preferences remain unchanged when viewing this page.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        } label: {
          Label("Current configuration", systemImage: "gearshape")
        }

        Spacer(minLength: 0)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("generalSettingsPage")
  }
}
