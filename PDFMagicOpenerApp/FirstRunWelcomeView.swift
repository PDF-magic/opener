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
  @State private var isSettingDefault = false
  @State private var defaultResultMessage: String?

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
            Text("Use Preferences to review your selected PDF viewer. This welcome preserves your viewer choice, and macOS’s default PDF association changes only if you explicitly request it below.")
            Text("You can decline any offer to make PDF Magic Opener your default PDF application and keep your current macOS PDF handler. Continuing to Preferences does not approve or make a default-handler change.")

            Label("Existing settings are preserved", systemImage: "gearshape")
              .font(.headline)
            Text("Continuing only opens Preferences. It does not install software, start scans, alter protection settings, or reset your customizations.")
          }
          .fixedSize(horizontal: false, vertical: true)

          VStack(alignment: .leading, spacing: 10) {
            Label("Default PDF app (optional)", systemImage: "doc.badge.gearshape")
              .font(.headline)
            Text("Make the installed PDF Magic Opener scan handler the macOS default for PDFs, or skip this step. Your chosen PDF viewer and scanning preferences are not changed.")
              .foregroundStyle(.secondary)
            Button("Set PDF Magic Opener as Default") {
              setDefaultPDFAppOnUserRequest()
            }
            .disabled(isSettingDefault)
            .accessibilityIdentifier("firstRunSetDefaultPDFAppButton")
            .accessibilityHint("Changes the macOS PDF association only when you choose this button.")

            if isSettingDefault {
              ProgressView("Verifying the installed PDF scan handler…")
            }

            if let defaultResultMessage {
              Text(defaultResultMessage)
                .font(.footnote)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("firstRunDefaultPDFAppResult")
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

  private func setDefaultPDFAppOnUserRequest() {
    guard !isSettingDefault else { return }
    isSettingDefault = true
    defaultResultMessage = nil
    // Reuse the installed scan-handler verifier; never register the
    // standalone preferences app or bypass the existing safety checks.
    PDFDefaultApplicationAction.request(
      at: PDFDefaultApplicationAction.installedHandler,
      runHelper: PDFDefaultApplicationAction.launchInstalledHelper,
      currentPDFHandler: PDFDefaultApplicationAction.currentPDFHandler
    ) { success in
      DispatchQueue.main.async {
        isSettingDefault = false
        defaultResultMessage = success
          ? "PDF Magic Opener is now the macOS default PDF application."
          : "The default could not be verified. Install the PDF Magic Opener scan handler or review the default PDF app in Preferences."
      }
    }
  }
}
