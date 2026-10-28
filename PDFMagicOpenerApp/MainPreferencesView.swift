import SwiftUI

// The main application preferences window is separate from the document
// opening/scanning process. Navigation is UI-only and never changes the
// configured PDF target, file associations, or security policy.
enum MainPreferenceSection: String, CaseIterable, Identifiable {
  case general
  case browsers
  case security

  var id: Self { self }

  var title: String {
    switch self {
    case .general: return "General"
    case .browsers: return "Browsers"
    case .security: return "Security"
    }
  }

  var symbolName: String {
    switch self {
    case .general: return "gearshape"
    case .browsers: return "globe"
    case .security: return "checkmark.shield"
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

  var body: some View {
    NavigationSplitView {
      List(MainPreferenceSection.allCases, selection: $selection) { section in
        Label(section.title, systemImage: section.symbolName)
          .tag(section)
      }
      .listStyle(.sidebar)
      .navigationTitle("Preferences")
      .frame(minWidth: 170)
      .accessibilityIdentifier("mainPreferencesSidebar")
    } detail: {
      currentPane
        .accessibilityIdentifier("mainPreferencesDetails")
    }
    .frame(minWidth: 680, minHeight: 420)
  }

  @ViewBuilder
  private var currentPane: some View {
    switch selection ?? .general {
    case .general:
      PreferenceOverviewPane(
        title: "PDF Magic Opener",
        description: "Preferences for the local document-opening workflow.",
        explanations: [
          PreferenceExplanation(
            title: "Opening documents",
            detail: "The installed PDF opener checks files before handing them to your chosen application."),
          PreferenceExplanation(
            title: "Existing configuration",
            detail: "Your current browser choices and application associations remain unchanged when viewing preferences."),
        ])
    case .browsers:
      PreferenceOverviewPane(
        title: "Browsers",
        description: "Manage where verified PDFs open using the existing browser preference tools.",
        explanations: [
          PreferenceExplanation(
            title: "Available applications",
            detail: "The installed browser preferences utility discovers available browsers and displays their versions."),
          PreferenceExplanation(
            title: "Saved choices",
            detail: "Opening this window never resets your configured destination or changes the system default browser."),
        ])
    case .security:
      PreferenceOverviewPane(
        title: "Security",
        description: "The PDF-opening safeguards continue to operate independently of this window.",
        explanations: [
          PreferenceExplanation(
            title: "Local scanning",
            detail: "The existing scan workflow checks documents with ClamAV before opening them."),
          PreferenceExplanation(
            title: "Verified handoff",
            detail: "The established native checks and quarantine protections are not bypassed by displaying preferences."),
        ])
    }
  }
}
