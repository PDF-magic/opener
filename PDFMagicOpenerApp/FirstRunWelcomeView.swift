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
  @State private var scannerInstallation: FirstRunScannerInstallation.Status?

  private var scannerInstallationMessage: String {
    switch scannerInstallation {
    case nil:
      return "Checking for the local ClamAV scanner and updater."
    case .some(.scannerMissing):
      return "ClamAV scanner not detected at a supported location. Install ClamAV before opening PDFs."
    case .some(.updaterMissing):
      return "ClamAV scanner detected, but its freshclam updater is missing or not executable. Complete the installation."
    case .some(.detected):
      return "ClamAV scanner and freshclam updater detected. This check does not verify their versions, signature freshness, or PDF safety."
    }
  }

  @State private var showingFinderQuickActionSetup = false
  @State private var installationHealth: FirstRunInstallationHealth?
  @State private var isSettingDefault = false
  @State private var defaultResultMessage: String?

  // Read existing installation metadata only. No scan, installation, PDF
  // association update, or browser preference write is performed.
  private func runBasicInstallationHealthCheck() {
    let signatures = FirstRunSignatureAvailability.readInstalled()
    signatureAvailability = signatures
    let signatureStatus: FirstRunInstallationHealth.SignatureFiles
    switch signatures {
    case .available: signatureStatus = .present
    case .missing: signatureStatus = .missing
    case .incomplete: signatureStatus = .incomplete
    case .unsafe: signatureStatus = .unsafe
    }

    let pdfAssociation: FirstRunInstallationHealth.PDFAssociation
    switch readGeneralPDFHandlerStatus() {
    case .isDefault: pdfAssociation = .opener
    case .other: pdfAssociation = .anotherApplication
    case .unknown: pdfAssociation = .unknown
    }

    installationHealth = FirstRunInstallationHealth.assess(
      handlerInstalled: PDFDefaultApplicationAction.verifiedHandler(
        at: PDFDefaultApplicationAction.installedHandler),
      signatureFiles: signatureStatus,
      pdfAssociation: pdfAssociation
    )
  }

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

          VStack(alignment: .leading, spacing: 8) {
            Label("Scanner installation check", systemImage: "checkmark.shield")
              .font(.headline)
            Text(scannerInstallationMessage)
              .foregroundStyle(.secondary)
              .accessibilityIdentifier("firstRunScannerInstallationStatus")
            Button("Check Scanner Again") {
              scannerInstallation = FirstRunScannerInstallation.check()
            }
            .accessibilityIdentifier("firstRunCheckScannerAgain")
          }

          VStack(alignment: .leading, spacing: 16) {
            Label("Local malware scanning", systemImage: "checkmark.shield")
              .font(.headline)
            Text("When PDFs are opened through the installed scan handler, a supported ClamAV scanner and recent malware definitions are required. If a scan cannot be verified, the handler blocks opening.")

            Label("Scanning cannot guarantee safety", systemImage: "exclamationmark.shield")
              .font(.headline)
            Text("A verified clean scan reduces risk, but ClamAV cannot detect every threat. A clean result does not guarantee that a PDF is safe; only open documents from sources you trust.")

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
            Text("Continuing saves only your preferred future protection level and opens Preferences. It does not install software, start scans, activate unavailable protection, change your PDF application, or reset your customizations.")

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

          GroupBox("Basic installation health check") {
            VStack(alignment: .leading, spacing: 10) {
              if let health = installationHealth {
                Text(health.summary)
                  .font(.headline)
                  .accessibilityIdentifier("firstRunInstallationHealthSummary")
                Label(health.handlerDetail, systemImage: "app.badge.checkmark")
                  .accessibilityIdentifier("firstRunInstallationHandlerStatus")
                Label(health.signatureDetail, systemImage: "checkmark.shield")
                  .accessibilityIdentifier("firstRunInstallationSignaturesStatus")
                Label(health.associationDetail, systemImage: "doc")
                  .accessibilityIdentifier("firstRunInstallationPDFAssociationStatus")
              } else {
                Text("Installation check has not run yet.")
                  .accessibilityIdentifier("firstRunInstallationHealthSummary")
              }
              Text(FirstRunInstallationHealth.caveat)
                .font(.footnote)
                .foregroundStyle(.secondary)
              Button("Check Installation Again", action: runBasicInstallationHealthCheck)
                .accessibilityIdentifier("firstRunCheckInstallationAgain")
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
          }
          .accessibilityIdentifier("firstRunInstallationHealthSection")

          // This is explanation only. Extension installation, activation and
          // browser permissions are always separate, user-controlled actions.
          GroupBox("Optional browser extensions") {
            VStack(alignment: .leading, spacing: 10) {
              Text("Browser extensions are optional. The installed native PDF handler can scan files opened through it without any browser extension.")
              Text("Current browser extensions are not active: they cannot scan, sanitize, or open PDFs, and have no verified browser-to-scanner connection. Installing one does not automatically protect PDFs viewed directly in a browser.")
              Text("This setup does not install or enable extensions, request browser permissions, or change browser settings. You can continue without an extension.")
                .foregroundStyle(.secondary)

              Divider()
              Label("Extension setup instructions", systemImage: "list.number")
                .font(.headline)
                .accessibilityIdentifier("firstRunExtensionSetupInstructions")

              Text("Safari (test builds): Install a properly signed PDF Magic Opener app with its Safari extension. In Safari, open Settings > Extensions, find PDF Magic Opener, and enable it manually if you choose. If it is not listed, check the installed host app.")
              Text("Chrome, Edge, Firefox, and other browsers: No public extension release is available. Current browser packages are for development and testing, not a ready-to-install protective extension.")
              Text("An enabled test extension still shows Not active and cannot scan or approve PDFs. Continue to use the installed native PDF handler for scanned opening; no extension installation or activation is performed here.")
                .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(8)
          }
          .accessibilityIdentifier("firstRunOptionalBrowserExtensions")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
      }

      Divider()

      HStack {
        Spacer()
        Button("Continue to Preferences", action: finishSetup)
          .disabled(initialProfile == nil)
          .disabled(savingBrowserChoice)
          .disabled(isSettingDefault)
          .keyboardShortcut(.defaultAction)
          .accessibilityIdentifier("firstRunContinueButton")
      }
    }
    .padding(28)
    .frame(minWidth: 680, minHeight: 420)
    .onAppear(perform: loadBrowserChoice)
    .onAppear(perform: runBasicInstallationHealthCheck)
    .accessibilityIdentifier("firstRunWelcomeScreen")
    .task {
      scannerInstallation = FirstRunScannerInstallation.check()
    }
  }
}
