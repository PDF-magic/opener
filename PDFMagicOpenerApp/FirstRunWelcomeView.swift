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
  @State private var showingFinderQuickActionSetup = false

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
            Text("You can decline any offer to make PDF Magic Opener your default PDF application and keep your current macOS PDF handler. Continuing to Preferences does not approve or make a default-handler change.")

            Label("Existing settings are preserved", systemImage: "gearshape")
              .font(.headline)
            Text("Continuing only opens Preferences. It does not install software, start scans, alter protection settings, or reset your customizations.")

            Label("Optional Finder Quick Action", systemImage: "folder")
              .font(.headline)
            Text("Would you like to configure the Finder “Allow and Open” Quick Action? This is optional. Your existing Finder actions are not changed by this welcome.")
            Button("Configure Finder Quick Action…") {
              showingFinderQuickActionSetup = true
            }
            .accessibilityIdentifier("firstRunConfigureFinderQuickActionButton")

            if showingFinderQuickActionSetup {
              VStack(alignment: .leading, spacing: 10) {
                Text("Finder Quick Action setup")
                  .font(.headline)
                Text("The installer requires an existing “Allow and Open” Quick Action. If it is missing, create a Quick Action with that name in Automator before installing. Do not replace a customized workflow.")
                Text("From a trusted PDF Magic Opener checkout, run bash install-allow-and-open.sh as your regular macOS user, without sudo. Follow its prompts. An unrecognized or customized Finder action is not silently replaced.")
                Link(
                  "Read the installation instructions",
                  destination: URL(string: "https://github.com/PDF-magic/opener#installation-and-usage")!
                )
                Button("Not now") {
                  showingFinderQuickActionSetup = false
                }
                .accessibilityIdentifier("firstRunDeferFinderQuickActionButton")
              }
              .padding(12)
              .frame(maxWidth: .infinity, alignment: .leading)
              .background(Color(nsColor: .controlBackgroundColor), in: RoundedRectangle(cornerRadius: 8))
              .accessibilityIdentifier("firstRunFinderQuickActionInstructions")
            }
          }
          .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }

      Divider()

      HStack {
        Spacer()
        Button("Continue to Preferences", action: onContinue)
          .keyboardShortcut(.defaultAction)
          .accessibilityIdentifier("firstRunContinueButton")
      }
    }
    .padding(28)
    .frame(minWidth: 680, minHeight: 420)
    .accessibilityIdentifier("firstRunWelcomeScreen")
  }
}
