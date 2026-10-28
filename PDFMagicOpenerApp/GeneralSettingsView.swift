import SwiftUI

// Only the explicit default-browser control may change the saved PDF target.
// It delegates validation and persistence to the existing installed helper.
// It does not change the macOS PDF handler, scanner, or quarantine protections.
struct GeneralSettingsView: View {
  @State private var browserOptions: [PDFBrowserOption] = []
  @State private var selectedBrowserID = ""
  @State private var browserMessage = ""
  @State private var savingBrowser = false
  @State private var loaded = false

  private func loadBrowserSelection() {
    guard !loaded else { return }
    loaded = true
    browserOptions = DefaultPDFBrowserPreferences.discover()
    if let saved = DefaultPDFBrowserPreferences.currentSelection() {
      selectedBrowserID = saved
    } else {
      browserMessage = "Current PDF browser preference could not be read. Nothing was changed."
    }
  }

  // A Picker change is an explicit user action, not an automatic save on view
  // appearance. The installed native chooser verifies PDF eligibility and
  // atomically persists target-app.txt; failure leaves selection unchanged.
  private func selectBrowser(_ identifier: String) {
    guard !savingBrowser, identifier != selectedBrowserID,
          let option = browserOptions.first(where: { $0.id == identifier }) else { return }
    savingBrowser = true
    browserMessage = "Verifying the selected browser…"
    DispatchQueue.global(qos: .userInitiated).async {
      let saved = DefaultPDFBrowserPreferences.saveVerified(option)
      DispatchQueue.main.async {
        savingBrowser = false
        if saved {
          selectedBrowserID = identifier
          browserMessage = "Default PDF browser saved."
        } else {
          browserMessage = "Could not verify or save that browser. Your previous choice is unchanged. Check that the PDF Magic Opener helper is installed."
        }
      }
    }
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("General")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Choose the browser that opens PDFs after the existing malware scan succeeds. Other settings remain unchanged.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox("Default PDF browser") {
          VStack(alignment: .leading, spacing: 10) {
            Picker("Browser for scanned PDFs", selection: Binding(
              get: { selectedBrowserID },
              set: { selectBrowser($0) }
            )) {
              Text("Choose an installed browser").tag("")
              ForEach(browserOptions) { option in
                Text(option.name).tag(option.id)
              }
              if !selectedBrowserID.isEmpty &&
                  !browserOptions.contains(where: { $0.id == selectedBrowserID }) {
                Text("Existing selection (not in installed browser list)").tag(selectedBrowserID)
              }
            }
            .disabled(savingBrowser || browserOptions.isEmpty)
            .accessibilityIdentifier("defaultPDFBrowserSelector")

            Text("Changes are saved only after the installed PDF application verifier approves the browser. Existing custom selections are retained unless explicitly replaced.")
              .font(.subheadline)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            if !browserMessage.isEmpty {
              Text(browserMessage)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("defaultPDFBrowserStatus")
            }
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("defaultPDFBrowserSection")

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
    .onAppear { loadBrowserSelection() }
  }
}
