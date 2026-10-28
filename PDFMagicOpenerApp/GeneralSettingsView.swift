import AppKit
import CoreServices
import SwiftUI
import UniformTypeIdentifiers

// Query the macOS *PDF* Launch Services association. The scanning helper
// owns this bundle ID; the standalone SwiftUI preferences app does not.
// This status lookup is read-only and can be injected for CI tests.
private let expectedPDFScanHandlerBundleID = "local.studio.brave-pdf-opener"

enum GeneralPDFHandlerStatus: Equatable {
  case isDefault
  case other(String)
  case unknown

  var title: String {
    switch self {
    case .isDefault: return "PDF Magic Opener is the default PDF handler"
    case .other: return "Another application is the default PDF handler"
    case .unknown: return "Default PDF handler could not be determined"
    }
  }

  var detail: String {
    switch self {
    case .isDefault:
      return "macOS routes PDFs to the installed PDF Magic Opener scanning handler."
    case .other(let identifier):
      return "Current handler: \(identifier). This status does not change your selected PDF application."
    case .unknown:
      return "macOS did not provide a valid PDF association. The default is not assumed to be PDF Magic Opener."
    }
  }

  var symbol: String {
    switch self {
    case .isDefault: return "checkmark.circle"
    case .other: return "info.circle"
    case .unknown: return "questionmark.circle"
    }
  }
}

func readGeneralPDFHandlerStatus(
  lookup: (String) -> String? = { contentType in
    LSCopyDefaultRoleHandlerForContentType(contentType as CFString, .all)?
      .takeRetainedValue() as String?
  }
) -> GeneralPDFHandlerStatus {
  guard let identifier = lookup(UTType.pdf.identifier),
        !identifier.isEmpty,
        identifier.contains("."),
        !identifier.contains(".."),
        !identifier.contains(where: { $0.isWhitespace || $0.isNewline }) else {
    return .unknown
  }

  return identifier == expectedPDFScanHandlerBundleID
    ? .isDefault : .other(identifier)
}

// Only the explicit default-browser control may change the saved PDF target.
// It delegates validation and persistence to the existing installed helper.
// It does not change the macOS PDF handler, scanner, or quarantine protections.
struct GeneralSettingsView: View {
  @State private var pdfHandlerStatus: GeneralPDFHandlerStatus = .unknown
  @State private var browserOptions: [PDFBrowserOption] = []
  @State private var selectedBrowserID = ""
  @State private var browserMessage = ""
  @State private var savingBrowser = false
  @State private var loaded = false

  private func refreshPDFHandlerStatus() {
    pdfHandlerStatus = readGeneralPDFHandlerStatus()
  }

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
  // atomically persists the installed PDF target; failure leaves it unchanged.
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
            Label(pdfHandlerStatus.title, systemImage: pdfHandlerStatus.symbol)
              .font(.headline)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("defaultPDFHandlerStatus")

            Text(pdfHandlerStatus.detail)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)

            Text("Read-only macOS PDF association status. The preferences app itself is not registered as a PDF handler.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        } label: {
          Label("Default PDF handler", systemImage: "doc.badge.gearshape")
        }
        .accessibilityIdentifier("defaultPDFHandlerSection")

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
    .onAppear(perform: refreshPDFHandlerStatus)
    .onReceive(NotificationCenter.default.publisher(
      for: NSApplication.didBecomeActiveNotification
    )) { _ in
      refreshPDFHandlerStatus()
    }
  }
}
