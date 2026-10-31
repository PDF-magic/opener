import SwiftUI

// The main preferences window displays a welcome before its first completed
// visit. The separate PDF scan handler never depends on this presentation UI.
struct FirstRunWelcomeGate<Content: View>: View {
  @State private var welcomePending = FirstRunWelcomeState.shouldShow()
  private let content: Content

  init(@ViewBuilder content: () -> Content) {
    self.content = content()
  }

  var body: some View {
    Group {
      if welcomePending {
        FirstRunWelcomeView {
          FirstRunWelcomeState.acknowledge()
          welcomePending = false
        }
      } else {
        content
      }
    }
  }
}

struct FirstRunWelcomeView: View {
  let onContinue: () -> Void
  @State private var initialProfile: PreferredProtectionLevel? =
    PlannedProtectionLevelPreference.selected()
  @State private var failedToSaveProfile = false

  private func finishSetup() {
    guard InitialProtectionProfileChoice.save(initialProfile) else {
      failedToSaveProfile = true
      return
    }
    // Only a verified preference save completes the welcome. The installed
    // scanner stays on Built-in ClamAV regardless of this planned choice.
    onContinue()
  }

  var body: some View {
    VStack(alignment: .leading, spacing: 16) {
      ScrollView {
        VStack(alignment: .leading, spacing: 20) {
          Label("Welcome to PDF Magic Opener", systemImage: "doc.text.magnifyingglass")
            .font(.largeTitle.weight(.semibold))
            .accessibilityAddTraits(.isHeader)

          Text("When configured as your PDF handler, PDF Magic Opener uses local ClamAV checks before opening a PDF in your chosen application. If a clean result and recent signatures cannot be verified, opening is blocked.")
            .font(.title3)
            .foregroundStyle(.secondary)

          VStack(alignment: .leading, spacing: 16) {
            Label("Local malware scanning", systemImage: "checkmark.shield")
              .font(.headline)
            Text("When PDFs are opened through the installed scan handler, a supported ClamAV scanner and recent malware definitions are required. If a scan cannot be verified, the handler blocks opening.")

            Label("Your choice of PDF application", systemImage: "macwindow")
              .font(.headline)
            Text("Use Preferences to review your selected PDF application and macOS default-handler status. This welcome does not change either selection.")

            Label("Existing settings are preserved", systemImage: "gearshape")
              .font(.headline)
            Text("Continuing saves only your preferred future protection level and opens Preferences. It does not install software, start scans, activate unavailable protection, change your PDF application, or reset your customizations.")
          }
          .fixedSize(horizontal: false, vertical: true)

          VStack(alignment: .leading, spacing: 10) {
            Label("Choose your initial protection preference", systemImage: "shield.lefthalf.filled")
              .font(.headline)
            Text("Built-in ClamAV scanning and fail-closed opening remain the only active protection. Standard, Enhanced and Maximum are future-profile preferences, not available scanner modes. Choosing one here does not enable its planned checks.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Picker("Preferred future protection profile", selection: $initialProfile) {
              Text("Not selected").tag(nil as PreferredProtectionLevel?)
              Text("Standard — baseline safeguards").tag(Optional(PreferredProtectionLevel.standard))
              Text("Enhanced — additional PDF checks planned").tag(Optional(PreferredProtectionLevel.enhanced))
              Text("Maximum — isolated analysis planned").tag(Optional(PreferredProtectionLevel.maximum))
            }
            .pickerStyle(.radioGroup)
            .accessibilityIdentifier("firstRunProtectionProfilePicker")

            if failedToSaveProfile {
              Text("Could not save your preference. Existing protection and settings are unchanged; please try again.")
                .foregroundStyle(.red)
                .accessibilityIdentifier("firstRunProtectionSaveError")
            }
          }
          .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }

      Divider()

      HStack {
        Spacer()
        Button("Continue to Preferences", action: finishSetup)
          .disabled(initialProfile == nil)
          .keyboardShortcut(.defaultAction)
          .accessibilityIdentifier("firstRunContinueButton")
      }
    }
    .padding(28)
    .frame(minWidth: 680, minHeight: 420)
    .accessibilityIdentifier("firstRunWelcomeScreen")
  }
}
