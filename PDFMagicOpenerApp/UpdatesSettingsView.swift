import SwiftUI

// An informational Updates page only. It must not download or install
// software, alter ClamAV definitions, or write to user preferences.
struct UpdatesSettingsView: View {
  @State private var checkingApplicationUpdates = false
  @State private var applicationUpdateMessage: String?
  @State private var updatingSignatures = false
  @State private var signatureUpdateMessage: String?

  private var applicationVersion: String {
    Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String
      ?? "Unavailable"
  }

  var body: some View {
    ScrollView {
      VStack(alignment: .leading, spacing: 20) {
        Text("Updates")
          .font(.largeTitle.weight(.semibold))
          .accessibilityAddTraits(.isHeader)

        Text("Application and malware-definition update information.")
          .foregroundStyle(.secondary)
          .fixedSize(horizontal: false, vertical: true)

        GroupBox("Application updates") {
          VStack(alignment: .leading, spacing: 10) {
            // Permit a stacked label/value when system text cannot fit
            // the default horizontal presentation.
            ViewThatFits(in: .horizontal) {
              LabeledContent("Installed version", value: applicationVersion)
              VStack(alignment: .leading, spacing: 4) {
                Text("Installed version")
                  .font(.headline)
                Text(applicationVersion)
                  .fixedSize(horizontal: false, vertical: true)
              }
              .frame(maxWidth: .infinity, alignment: .leading)
            }

            Button("Check for Updates Now") {
              checkingApplicationUpdates = true
              applicationUpdateMessage = nil
              Task {
                applicationUpdateMessage = await ManualUpdateActions.checkApplicationUpdates(
                  installedVersion: applicationVersion
                )
                checkingApplicationUpdates = false
              }
            }
            .disabled(checkingApplicationUpdates)
            .accessibilityIdentifier("checkForUpdatesNowButton")
            if checkingApplicationUpdates {
              ProgressView("Checking published releases…")
            }
            if let applicationUpdateMessage {
              Text(applicationUpdateMessage)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("applicationUpdateCheckResult")
            }

            Label("The installed version comes from this app bundle. It does not tell you whether newer software exists.", systemImage: "info.circle")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("applicationUpdatesSection")

        GroupBox("Malware definition updates") {
          VStack(alignment: .leading, spacing: 10) {
            Button("Update Signatures Now") {
              updatingSignatures = true
              signatureUpdateMessage = nil
              Task {
                signatureUpdateMessage = await ManualUpdateActions.updateSignatures()
                updatingSignatures = false
              }
            }
            .disabled(updatingSignatures)
            .accessibilityIdentifier("updateSignaturesNowButton")
            if updatingSignatures {
              ProgressView("Updating malware definitions…")
            }
            if let signatureUpdateMessage {
              Text(signatureUpdateMessage)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("signatureUpdateActionResult")
            }
            Text("Manual updates reuse the installed FreshClam updater. They never approve a file or bypass scanner checks.")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Text("ClamAV malware definitions are maintained by the existing scanner update workflow, independently of these application preferences. Manual updating is optional; the scanner still checks freshness before every open.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Label("Malware definitions describe threats recognized by the scanner. Their update schedule is separate from app updates, and this page cannot confirm when they were last refreshed.", systemImage: "info.circle")
              .font(.footnote)
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
          }
          .frame(maxWidth: .infinity, alignment: .leading)
          .padding(8)
        }
        .accessibilityIdentifier("malwareDefinitionUpdatesSection")

        Spacer(minLength: 0)
      }
      .padding(28)
      .frame(maxWidth: .infinity, alignment: .leading)
    }
    .accessibilityIdentifier("updatesSettingsPage")
  }
}


import Foundation
import Darwin

// Both operations require an explicit click. Never run from .onAppear or
// the PDF scanning path. Neither a release result nor FreshClam's exit code
// authorizes opening a document.
enum ManualUpdateActions {
  static let releaseURL = URL(string: "https://api.github.com/repos/PDF-magic/opener/releases/latest")!

  private static func components(_ raw: String) -> [Int]? {
    let version = raw.hasPrefix("v") ? String(raw.dropFirst()) : raw
    let parts = version.split(separator: ".", omittingEmptySubsequences: false)
    guard (1...3).contains(parts.count) else { return nil }
    var numbers: [Int] = []
    for part in parts {
      guard !part.isEmpty, part.allSatisfy({ $0.isASCII && $0.isNumber }),
            let number = Int(part), number <= 999_999 else { return nil }
      numbers.append(number)
    }
    while numbers.count < 3 { numbers.append(0) }
    return numbers
  }

  static func releaseMessage(data: Data, installedVersion: String) -> String {
    guard let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
          let tag = object["tag_name"] as? String,
          let remote = components(tag) else {
      return "Release information could not be verified."
    }
    guard let installed = components(installedVersion) else {
      return "Published version \(tag) found, but the installed version cannot be compared."
    }
    if remote.lexicographicallyPrecedes(installed) || remote == installed {
      return "No newer published application release was found (latest: \(tag))."
    }
    return "Application release \(tag) is available. Installation is not automatic."
  }

  static func checkApplicationUpdates(installedVersion: String) async -> String {
    var request = URLRequest(url: releaseURL)
    request.timeoutInterval = 15
    request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
    do {
      let (data, response) = try await URLSession.shared.data(for: request)
      guard let http = response as? HTTPURLResponse else {
        return "Could not verify application releases."
      }
      if http.statusCode == 404 {
        return "No published application release is available for comparison."
      }
      guard http.statusCode == 200, data.count <= 65_536 else {
        return "Could not verify application releases."
      }
      return releaseMessage(data: data, installedVersion: installedVersion)
    } catch {
      return "Could not check for application updates. Please try again later."
    }
  }

  static func updateSignatures() async -> String {
    await Task.detached(priority: .userInitiated) {
      let script = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/Studio/allow-and-open/update-malware-signatures.sh")
      var metadata = stat()
      guard lstat(script.path, &metadata) == 0,
            (metadata.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else {
        return "Installed signature updater unavailable. Reinstall the scanner to restore it."
      }
      let process = Process()
      process.executableURL = URL(fileURLWithPath: "/bin/bash")
      process.arguments = [script.path]
      // Never display FreshClam logs, local file paths or configuration.
      process.standardOutput = FileHandle.nullDevice
      process.standardError = FileHandle.nullDevice
      do {
        try process.run()
        process.waitUntilExit()
        return process.terminationReason == .exit && process.terminationStatus == 0
          ? "Signature update completed. Scanner freshness checks still apply."
          : "Signature update failed. Existing scanner protections remain active."
      } catch {
        return "Could not start the installed signature updater."
      }
    }.value
  }
}
