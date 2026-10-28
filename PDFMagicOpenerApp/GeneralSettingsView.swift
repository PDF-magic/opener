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

// General preferences are informational until configuration workflows are
// implemented. Never mutate the active PDF handler, saved browser, or scanner.
struct GeneralSettingsView: View {
  @State private var pdfHandlerStatus: GeneralPDFHandlerStatus = .unknown

  private func refreshPDFHandlerStatus() {
    pdfHandlerStatus = readGeneralPDFHandlerStatus()
  }

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
    .onAppear(perform: refreshPDFHandlerStatus)
    .onReceive(NotificationCenter.default.publisher(
      for: NSApplication.didBecomeActiveNotification
    )) { _ in
      refreshPDFHandlerStatus()
    }
  }
}
