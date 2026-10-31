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
  @State private var signatureAvailability = FirstRunSignatureAvailability.readInstalled()
  @State private var isSettingDefault = false
  @State private var defaultResultMessage: String?

  @State private var installedBrowserOptions: [PDFBrowserOption] = []
  @State private var savedBrowserID = ""
  @State private var selectedBrowserID = ""
  @State private var browserChoiceStatus = ""
  @State private var savingBrowserChoice = false
  @State private var browserChoiceLoaded = false

  private func loadBrowserChoice() {
    // Inspect existing preferences only. Merely seeing the welcome must never
    // replace a previous custom choice or write to scanner configuration.
    guard !browserChoiceLoaded else { return }
    browserChoiceLoaded = true
    installedBrowserOptions = DefaultPDFBrowserPreferences.discover()
    if let existing = DefaultPDFBrowserPreferences.currentSelection() {
      savedBrowserID = existing
      selectedBrowserID = existing
    } else {
      browserChoiceStatus = "The current PDF browser preference could not be read. Nothing was changed."
    }
  }

  private func saveBrowserChoice() {
    guard !savingBrowserChoice, selectedBrowserID != savedBrowserID,
          let option = installedBrowserOptions.first(where: { $0.id == selectedBrowserID }) else {
      return
    }
    savingBrowserChoice = true
    browserChoiceStatus = "Verifying the selected browser…"
    // Reuse the existing installed, verified atomic chooser. In particular,
    // do not write target preferences, bypass PDF verification or change the
    // macOS default handler from the preferences application.
    DispatchQueue.global(qos: .userInitiated).async {
      let saved = DefaultPDFBrowserPreferences.saveVerified(option)
      DispatchQueue.main.async {
        savingBrowserChoice = false
        if saved {
          savedBrowserID = option.id
          selectedBrowserID = option.id
          browserChoiceStatus = "Default PDF browser saved."
        } else {
          selectedBrowserID = savedBrowserID
          browserChoiceStatus = "Could not verify or save that browser. Your previous choice is unchanged. Check that the PDF Magic Opener helper is installed."
        }
      }
    }
  }

  private func setDefaultPDFAppOnUserRequest() {
    guard !isSettingDefault && !savingBrowserChoice else { return }
    isSettingDefault = true
    defaultResultMessage = nil
    // Reuse the installed scan-handler verifier. Never register this
    // standalone preferences app or bypass existing PDF scan protections.
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

            Label("Signature availability", systemImage: "checkmark.shield")
              .font(.headline)
            Text(signatureAvailability.explanation)
              .accessibilityIdentifier("firstRunSignatureAvailability")
            Button("Check Signature Files Again") {
              signatureAvailability = FirstRunSignatureAvailability.readInstalled()
            }
            .accessibilityIdentifier("firstRunRecheckSignatures")

            Label("Your choice of PDF application", systemImage: "macwindow")
              .font(.headline)
            Text("This welcome does not change either selection automatically. You can explicitly save a verified PDF browser choice below, or separately make PDF Magic Opener the macOS default PDF handler.")
            Text("You can decline any offer to make PDF Magic Opener your default PDF application and keep your current macOS PDF handler. Continuing to Preferences does not approve or make a default-handler change.")

            Label("Existing settings are preserved", systemImage: "gearshape")
              .font(.headline)
            Text("Continuing only opens Preferences. It does not install software, start scans, alter protection settings, or reset your customizations.")
          }
          .fixedSize(horizontal: false, vertical: true)

          GroupBox("Default PDF browser") {
            VStack(alignment: .leading, spacing: 10) {
              Text("Choose which browser opens PDFs after a successful scan. This does not change the macOS default PDF handler.")
                .foregroundStyle(.secondary)

              Picker("Browser for scanned PDFs", selection: $selectedBrowserID) {
                Text("Choose an installed browser").tag("")
                ForEach(installedBrowserOptions) { option in
                  Text(option.name).tag(option.id)
                }
                if !savedBrowserID.isEmpty &&
                    !installedBrowserOptions.contains(where: { $0.id == savedBrowserID }) {
                  Text("Existing custom or unavailable selection (preserved)").tag(savedBrowserID)
                }
              }
              .disabled(savingBrowserChoice || installedBrowserOptions.isEmpty)
              .accessibilityIdentifier("firstRunPDFBrowserSelector")

              HStack {
                Button("Save browser choice", action: saveBrowserChoice)
                  .disabled(savingBrowserChoice ||
                    selectedBrowserID == savedBrowserID ||
                    !installedBrowserOptions.contains(where: { $0.id == selectedBrowserID }))
                  .accessibilityIdentifier("firstRunSavePDFBrowserButton")

                Text("Optional. Continue without saving to keep your current choice.")
                  .font(.subheadline)
                  .foregroundStyle(.secondary)
              }

              if !browserChoiceStatus.isEmpty {
                Text(browserChoiceStatus)
                  .font(.subheadline)
                  .foregroundStyle(.secondary)
                  .accessibilityIdentifier("firstRunPDFBrowserStatus")
              }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
          }
          .accessibilityIdentifier("firstRunPDFBrowserSection")

          GroupBox("Default PDF application (optional)") {
            VStack(alignment: .leading, spacing: 10) {
              Text("Make the installed PDF Magic Opener scan handler the macOS default for PDFs, or skip this step. Your chosen PDF viewer and scanning preferences are not changed.")
                .foregroundStyle(.secondary)

              Button("Set PDF Magic Opener as Default") {
                setDefaultPDFAppOnUserRequest()
              }
              .disabled(isSettingDefault || savingBrowserChoice)
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
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
          }
          .accessibilityIdentifier("firstRunDefaultPDFAppSection")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }

      Divider()

      HStack {
        Spacer()
        Button("Continue to Preferences", action: onContinue)
          .disabled(savingBrowserChoice)
          .disabled(isSettingDefault)
          .keyboardShortcut(.defaultAction)
          .accessibilityIdentifier("firstRunContinueButton")
      }
    }
    .padding(28)
    .frame(minWidth: 680, minHeight: 420)
    .onAppear(perform: loadBrowserChoice)
    .accessibilityIdentifier("firstRunWelcomeScreen")
  }
}
