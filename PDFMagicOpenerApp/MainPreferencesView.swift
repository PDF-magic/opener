import SwiftUI

// The main application preferences window is separate from the document
// opening/scanning process. Navigation is UI-only and never changes the
// configured PDF target, file associations, or security policy.
enum MainPreferenceSection: String, CaseIterable, Identifiable {
  case general
  case browsers
  case security
  case advancedScanning
  case updates
  case aboutAndDiagnostics
  case extensionsAndIntegrations
  case privacyAndLogs

  var id: Self { self }

  var title: String {
    switch self {
    case .general: return "General"
    case .browsers: return "Browsers"
    case .security: return "Protection"
    case .advancedScanning: return "Advanced Scanning"
    case .updates: return "Updates"
    case .aboutAndDiagnostics: return "About and Diagnostics"
    case .extensionsAndIntegrations: return "Extensions and Integrations"
    case .privacyAndLogs: return "Privacy and Logs"
    }
  }

  var symbolName: String {
    switch self {
    case .general: return "gearshape"
    case .browsers: return "globe"
    case .security: return "checkmark.shield"
    case .advancedScanning: return "magnifyingglass.circle"
    case .updates: return "arrow.triangle.2.circlepath"
    case .aboutAndDiagnostics: return "info.circle"
    case .extensionsAndIntegrations: return "puzzlepiece.extension"
    case .privacyAndLogs: return "hand.raised"
    }
  }
}

private struct PreferenceExplanation: Identifiable {
  let title: String
  let detail: String
  var id: String { title }
}

private struct PreferenceOverviewPane: View {
  let title: String
  let description: String
  let explanations: [PreferenceExplanation]

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text(title)
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)
        Text(description)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        ForEach(explanations) { item in
          VStack(alignment: .leading, spacing: 6) {
            Text(item.title).font(.headline)
            Text(item.detail)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(16)
          .background(Color(nsColor: .controlBackgroundColor),
                      in: RoundedRectangle(cornerRadius: 10))
        }
        Spacer(minLength: 0)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
  }
}

struct MainPreferencesView: View {
  @State private var selection: MainPreferenceSection? = .general
  @State private var showResetToDefaultsConfirmation = false
  @State private var showResetToDefaultsResult = false
  @State private var resetToDefaultsResult = ""
  @State private var resetRevision = 0
  // Follow increased macOS system text sizes rather than assuming a fixed
  // 170-point sidebar can fit every label.
  @ScaledMetric(relativeTo: .body) private var sidebarMinimumWidth: CGFloat = 230
  @FocusState private var sidebarFocused: Bool

  private var selectedIndex: Int {
    MainPreferenceSection.allCases.firstIndex(of: selection ?? .general) ?? 0
  }

  // Keyboard shortcuts change only the in-memory page selection. Respect
  // the bounds, including newly added preferences destinations.
  private func moveSelection(by offset: Int) {
    let sections = MainPreferenceSection.allCases
    let nextIndex = selectedIndex + offset
    guard sections.indices.contains(nextIndex) else { return }
    selection = sections[nextIndex]
    sidebarFocused = true
  }

  // Reset only persisted preferences represented by the current configuration
  // schema. PDF targets, user-selected applications and scanner policy are
  // intentionally managed by separate, verified workflows.
  private func resetToDefaults() {
    if GeneralPreferencesReset.reset() {
      // Recreate General so its existing onAppear readers show current values.
      resetRevision += 1
      resetToDefaultsResult = "Scan progress and notification preferences restored to defaults. Your selected PDF browser, PDF handler and scanner protections were not changed."
    } else {
      resetToDefaultsResult = "Could not reset saved preferences. Check the existing settings before trying again."
    }
    showResetToDefaultsResult = true
  }

  var body: some View {
    NavigationSplitView {
      List(MainPreferenceSection.allCases, selection: $selection) { section in
        Label(section.title, systemImage: section.symbolName)
          .lineLimit(nil)
          .fixedSize(horizontal: false, vertical: true)
          .tag(section)
          // Read the page title, not the decorative SF Symbol name.
          .accessibilityLabel("\(section.title) settings")
          .accessibilityHint("Show the \(section.title) settings page")
      }
      .listStyle(.sidebar)
      .accessibilityLabel("Preferences sections")
      .focused($sidebarFocused)
      .onAppear { sidebarFocused = true }
      .navigationTitle("Preferences")
      .frame(minWidth: sidebarMinimumWidth)
      .accessibilityIdentifier("mainPreferencesSidebar")
    } detail: {
      currentPane
        .accessibilityIdentifier("mainPreferencesDetails")
    }
    .frame(minWidth: 680, minHeight: 420)
    .toolbar {
      ToolbarItemGroup {
        Button {
          moveSelection(by: -1)
        } label: {
          Label("Previous Section", systemImage: "chevron.up")
        }
        .keyboardShortcut("[", modifiers: .command)
        .disabled(selectedIndex == 0)
        .help("Previous preferences section (Command-[)")

        Button {
          moveSelection(by: 1)
        } label: {
          Label("Next Section", systemImage: "chevron.down")
        }
        .keyboardShortcut("]", modifiers: .command)
        .disabled(selectedIndex == MainPreferenceSection.allCases.count - 1)
        .help("Next preferences section (Command-])")
      }
      ToolbarItem(placement: .primaryAction) {
        Button("Reset to Defaults") {
          showResetToDefaultsConfirmation = true
        }
        .accessibilityIdentifier("resetToDefaultsButton")
        .help("Restore scan display and notification defaults without changing your PDF browser or scanner")
      }
    }
    .confirmationDialog(
      "Reset saved preferences to defaults?",
      isPresented: $showResetToDefaultsConfirmation,
      titleVisibility: .visible
    ) {
      Button("Reset to Defaults", role: .destructive) {
        resetToDefaults()
      }
      Button("Cancel", role: .cancel) {}
    } message: {
      Text("Restore scan progress to on and successful-scan and blocked-file notifications to off. Your selected PDF browser, macOS PDF handler, scanner protections and unrelated customizations remain unchanged.")
    }
    .alert("Reset to Defaults", isPresented: $showResetToDefaultsResult) {
      Button("OK", role: .cancel) {}
    } message: {
      Text(resetToDefaultsResult)
    }
  }

  @ViewBuilder
  private var currentPane: some View {
    switch selection ?? .general {
    case .general:
      GeneralSettingsView()
        .id(resetRevision)
    case .browsers:
      BrowsersSettingsView()
    case .security:
      ProtectionSettingsView()
    case .advancedScanning:
      AdvancedScanningSettingsView()
    case .updates:
      UpdatesSettingsView()
    case .aboutAndDiagnostics:
      AboutAndDiagnosticsSettingsView()
    case .extensionsAndIntegrations:
      ExtensionsAndIntegrationsSettingsView()
    case .privacyAndLogs:
      PrivacyAndLogsSettingsView()
    }
  }
}
