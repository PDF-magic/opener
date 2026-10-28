import AppKit
import CoreServices
import SwiftUI
import UniformTypeIdentifiers

// The standalone settings app does not handle PDFs. Only the separately
// installed, scanner-gated PDF handler may become the system PDF default.
enum PDFDefaultApplicationAction {
  static let handlerBundleID = "local.studio.brave-pdf-opener"

  static var installedHandler: URL {
    FileManager.default.homeDirectoryForCurrentUser
      .appendingPathComponent("Applications/PDF Magic Opener.app", isDirectory: true)
  }

  static func verifiedHandler(at application: URL, files: FileManager = .default) -> Bool {
    guard application.lastPathComponent == "PDF Magic Opener.app",
          (try? files.destinationOfSymbolicLink(atPath: application.path)) == nil,
          let attributes = try? files.attributesOfItem(atPath: application.path),
          attributes[.type] as? FileAttributeType == .typeDirectory,
          let bundle = Bundle(url: application),
          bundle.bundleIdentifier == handlerBundleID,
          let executable = bundle.executableURL,
          files.isExecutableFile(atPath: executable.path),
          let declarations = bundle.object(forInfoDictionaryKey: "CFBundleDocumentTypes")
            as? [[String: Any]] else { return false }

    return declarations.contains { declaration in
      (declaration["LSItemContentTypes"] as? [String])?.contains("com.adobe.pdf") == true
    }
  }

  // Dependency injection makes regression tests safe: they never alter the
  // CI runner's Launch Services associations or execute an installed helper.
  static func request(
    at application: URL,
    runHelper: (URL, @escaping (Bool) -> Void) -> Void,
    currentPDFHandler: @escaping () -> String?,
    completion: @escaping (Bool) -> Void
  ) {
    guard verifiedHandler(at: application) else {
      completion(false)
      return
    }
    runHelper(application) { helperSucceeded in
      guard helperSucceeded else {
        completion(false)
        return
      }
      // A successful helper exit alone does not establish a changed default.
      completion(currentPDFHandler() == handlerBundleID)
    }
  }

  static func currentPDFHandler() -> String? {
    LSCopyDefaultRoleHandlerForContentType(UTType.pdf.identifier as CFString, .all)?
      .takeRetainedValue() as String?
  }

  static func launchInstalledHelper(at application: URL, completion: @escaping (Bool) -> Void) {
    let helper = application.appendingPathComponent("Contents/MacOS/MakePDFMagicDefault")
    let files = FileManager.default
    guard verifiedHandler(at: application, files: files),
          (try? files.destinationOfSymbolicLink(atPath: helper.path)) == nil,
          files.isExecutableFile(atPath: helper.path) else {
      completion(false)
      return
    }

    let process = Process()
    process.executableURL = helper
    process.arguments = [] // No shell, document paths, or user-supplied app IDs.
    process.terminationHandler = { finished in
      DispatchQueue.main.async {
        completion(finished.terminationReason == .exit && finished.terminationStatus == 0)
      }
    }
    do {
      try process.run()
    } catch {
      completion(false)
    }
  }
}

struct PDFDefaultApplicationSettingsView: View {
  @State private var isSettingDefault = false
  @State private var resultMessage: String?

  var body: some View {
    GroupBox("Default PDF application") {
      VStack(alignment: .leading, spacing: 12) {
        Text("Choose PDF Magic Opener as the macOS app for opening PDFs. The separately installed PDF handler scans files before handing verified documents to your selected viewer.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        Button("Set as Default PDF App") {
          setDefaultOnUserRequest()
        }
        .disabled(isSettingDefault)
        .accessibilityIdentifier("setDefaultPDFAppButton")
        .accessibilityHint("Changes the macOS PDF file association only after you choose this action.")

        if isSettingDefault {
          ProgressView("Changing default PDF application…")
        }

        if let resultMessage {
          Text(resultMessage)
            .font(.footnote)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("setDefaultPDFAppResult")
        }

        Text("Requires the installed PDF Magic Opener scan handler. This does not change your selected browser, scanning policy, or other file defaults.")
          .font(.footnote)
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)
      }
      .frame(maxWidth: .infinity, alignment: .leading)
      .padding(8)
    }
    .accessibilityIdentifier("defaultPDFApplicationSection")
  }

  private func setDefaultOnUserRequest() {
    guard !isSettingDefault else { return }
    isSettingDefault = true
    resultMessage = nil
    PDFDefaultApplicationAction.request(
      at: PDFDefaultApplicationAction.installedHandler,
      runHelper: PDFDefaultApplicationAction.launchInstalledHelper,
      currentPDFHandler: PDFDefaultApplicationAction.currentPDFHandler
    ) { success in
      DispatchQueue.main.async {
        isSettingDefault = false
        resultMessage = success
          ? "PDF Magic Opener is now the default PDF application."
          : "Could not verify the change. Install the PDF Magic Opener scan handler or choose a PDF app in Finder’s Get Info."
      }
    }
  }
}
