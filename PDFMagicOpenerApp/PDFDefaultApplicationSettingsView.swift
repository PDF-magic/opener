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

  
// The installed history utility alone validates the protected previous
// application and changes the system PDF association. This UI never does.
enum PDFPreviousDefaultRestoreAction {
  static let historyCommand = "pdf-handler-history"
  static let historyFilename = "previous-pdf-handler.txt"

  static func request(
    currentPDFHandler: @escaping () -> String?,
    runHelper: (@escaping (Bool) -> Void) -> Void,
    completion: @escaping (Bool) -> Void
  ) {
    // Fail closed when a user changed their default after installation.
    guard currentPDFHandler() == PDFDefaultApplicationAction.handlerBundleID else {
      completion(false)
      return
    }
    runHelper { success in
      guard success,
            let observed = currentPDFHandler(),
            !observed.isEmpty,
            observed != PDFDefaultApplicationAction.handlerBundleID else {
        completion(false)
        return
      }
      // The native helper separately verifies that observed == saved history.
      completion(true)
    }
  }

  static func launchInstalledHelper(completion: @escaping (Bool) -> Void) {
    let files = FileManager.default
    let folder = files.homeDirectoryForCurrentUser
      .appendingPathComponent("Library/Application Support/Studio/allow-and-open", isDirectory: true)
    let helper = folder.appendingPathComponent(historyCommand)
    let history = folder.appendingPathComponent(historyFilename)

    guard (try? files.destinationOfSymbolicLink(atPath: folder.path)) == nil,
          (try? files.destinationOfSymbolicLink(atPath: helper.path)) == nil,
          let folderAttributes = try? files.attributesOfItem(atPath: folder.path),
          folderAttributes[.type] as? FileAttributeType == .typeDirectory,
          let attributes = try? files.attributesOfItem(atPath: helper.path),
          attributes[.type] as? FileAttributeType == .typeRegular,
          files.isExecutableFile(atPath: helper.path) else {
      completion(false)
      return
    }

    // The installed tool checks history file type, permissions, bundle
    // identity, installation validity, and current association again.
    let process = Process()
    process.executableURL = helper
    process.arguments = ["restore", history.path] // No shell or user-supplied command.
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
  @State private var showingRestoreConfirmation = false
  @State private var isRestoringDefault = false
  @State private var restoreResultMessage: String?

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
        .disabled(isRestoringDefault)
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


        Button("Restore Previous Default") {
          showingRestoreConfirmation = true
        }
        .disabled(isSettingDefault || isRestoringDefault)
        .accessibilityIdentifier("restorePreviousDefaultPDFAppButton")
        .accessibilityHint("Restore the PDF application recorded before PDF Magic Opener.")
        .confirmationDialog(
          "Restore the previous default PDF application?",
          isPresented: $showingRestoreConfirmation
        ) {
          Button("Restore Previous Default", role: .destructive) {
            restorePreviousOnUserRequest()
          }
          Button("Cancel", role: .cancel) {}
        } message: {
          Text("Restoring the prior PDF app removes PDF Magic Opener from the default PDF-opening path, so its automatic scan gate will no longer run for PDFs opened by default. Only the recorded, verified app can be restored. Your selected browser and scanner settings will not change.")
        }

        if isRestoringDefault {
          ProgressView("Restoring previous PDF default…")
        }

        if let restoreResultMessage {
          Text(restoreResultMessage)
            .font(.footnote)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityIdentifier("restorePreviousDefaultResult")
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
    guard !isSettingDefault && !isRestoringDefault else { return }
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
  private func restorePreviousOnUserRequest() {
    guard !isSettingDefault && !isRestoringDefault else { return }
    isRestoringDefault = true
    restoreResultMessage = nil
    PDFPreviousDefaultRestoreAction.request(
      currentPDFHandler: PDFDefaultApplicationAction.currentPDFHandler,
      runHelper: PDFPreviousDefaultRestoreAction.launchInstalledHelper
    ) { success in
      DispatchQueue.main.async {
        isRestoringDefault = false
        restoreResultMessage = success
          ? "Previous PDF default restored."
          : "Unable to restore the recorded previous PDF app. The installed history must be valid and PDF Magic Opener must still be the current default."
      }
    }
  }

}
