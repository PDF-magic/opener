import SwiftUI

// Status is read-only; only explicit actions can check revisions or start
// the already-installed updater. Scanner protections remain unchanged.
struct UpdatesSettingsView: View {
  @State private var checkingSignatureUpdates = false
  @State private var signatureCheckMessage: String?
  @State private var updatingSignatures = false
  @State private var signatureUpdateMessage: String?

  @State private var signatureStatus = SignatureUpdateStatus.readInstalled()

  // A read-only snapshot taken when the Updates pane is constructed.
  // Times are displayed in the user's local time zone; "Unavailable" is
  // intentional for older installations or invalid/unreadable markers.
  private func timestampRow(_ label: String, _ date: Date?) -> some View {
    let value = date.map { $0.formatted(date: .abbreviated, time: .standard) }
      ?? "Unavailable"
    return ViewThatFits(in: .horizontal) {
      LabeledContent(label, value: value)
      VStack(alignment: .leading, spacing: 4) {
        Text(label).font(.headline)
        Text(value).fixedSize(horizontal: false, vertical: true)
      }
    }
  }

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

            Text("Checking for or installing application updates is not available from this page yet.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
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
            // The installed FreshClam agent may update signatures even when
            // no manual action is active. Show only observed, live progress.
            TimelineView(.periodic(from: .now, by: 2)) { timeline in
              if let active = SignatureUpdateProgress.readInstalled(now: timeline.date) {
                HStack(alignment: .center, spacing: 12) {
                  ProgressView()
                    .progressViewStyle(.circular)
                    .accessibilityHidden(true)
                  VStack(alignment: .leading, spacing: 4) {
                    Text("Signature update in progress")
                      .font(.headline)
                    Text("Checking and downloading ClamAV definitions…")
                      .foregroundStyle(.secondary)
                    Text("Started at " + active.startedAt.formatted(date: .abbreviated, time: .standard))
                      .font(.footnote)
                      .foregroundStyle(.secondary)
                  }
                  .fixedSize(horizontal: false, vertical: true)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("signatureUpdateProgress")
              } else if !updatingSignatures {
                Text("No active signature update detected.")
                  .foregroundStyle(.secondary)
                  .accessibilityIdentifier("signatureUpdateIdle")
              }
            }
            Text(signatureStatus.message)
              .font(.headline)
              .fixedSize(horizontal: false, vertical: true)
              .accessibilityIdentifier("signatureUpdateSummary")
            if let failure = signatureStatus.lastFailure {
              VStack(alignment: .leading, spacing: 6) {
                Label("Signature update failure recorded", systemImage: "exclamationmark.triangle")
                  .font(.headline)
                Text(signatureStatus.failureExplanation ?? "An earlier signature update failed.")
                  .fixedSize(horizontal: false, vertical: true)
                timestampRow("Last failed update", failure)
                if !signatureStatus.hasUnresolvedFailure {
                  Text("A successful update was recorded after this failure.")
                    .foregroundStyle(.secondary)
                }
                Text("This failure record contains no FreshClam logs or private file paths.")
                  .font(.footnote)
                  .foregroundStyle(.secondary)
              }
              .accessibilityElement(children: .combine)
              .accessibilityIdentifier("signatureUpdateFailure")
            }
            timestampRow("Last attempted update", signatureStatus.lastAttempt)
              .accessibilityIdentifier("signatureUpdateLastAttempt")
            timestampRow("Last successful update", signatureStatus.lastSuccess)
              .accessibilityIdentifier("signatureUpdateLastSuccess")
            Text("Times are shown in your local time zone.")
              .font(.footnote)
              .foregroundStyle(.secondary)
            Button("Check for Updates Now") {
              checkingSignatureUpdates = true
              signatureCheckMessage = nil
              Task {
                signatureCheckMessage = await ManualUpdateActions.checkSignatureUpdates()
                checkingSignatureUpdates = false
              }
            }
            .disabled(checkingSignatureUpdates)
            .accessibilityIdentifier("checkForUpdatesNowButton")
            if checkingSignatureUpdates {
              ProgressView("Checking published signature revisions…")
            }
            if let signatureCheckMessage {
              Text(signatureCheckMessage)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("signatureUpdateCheckResult")
            }
            Button("Update Signatures Now") {
              updatingSignatures = true
              signatureUpdateMessage = nil
              Task {
                signatureUpdateMessage = await ManualUpdateActions.updateSignatures()
                signatureStatus = SignatureUpdateStatus.readInstalled()
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
            Text("ClamAV definitions are maintained by the existing scanner update workflow independently of these preferences. These timestamps do not verify signature freshness or database health.")
              .foregroundStyle(.secondary)
              .fixedSize(horizontal: false, vertical: true)
            Label("Malware definitions describe threats recognized by the scanner. Their update schedule is separate from app updates. An attempted update is not proof of success. The installed scanner still checks signature freshness and database validity before scanning; viewing this page never starts an update.", systemImage: "info.circle")
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

// Both actions require a click and never participate in document scanning.
// Checking reads only published revision numbers and local database headers;
// updating delegates to the separately installed FreshClam script.
enum ManualUpdateActions {
  static func publishedRevisions(from output: String) -> (main: Int, daily: Int)? {
    let records = output.split(whereSeparator: \.isNewline)
    guard records.count == 1 else { return nil }
    let record = String(records[0])
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .trimmingCharacters(in: CharacterSet(charactersIn: "\""))
    let fields = record.split(separator: ":", omittingEmptySubsequences: false)
    guard fields.count >= 3, fields[0].contains("."),
          let main = Int(fields[1]), let daily = Int(fields[2]),
          main > 0, daily > 0, main <= 999_999_999,
          daily <= 999_999_999 else { return nil }
    return (main, daily)
  }

  static func databaseRevision(header: Data) -> Int? {
    guard header.count >= 32,
          let text = String(data: header.prefix(512), encoding: .ascii),
          text.hasPrefix("ClamAV-VDB:") else { return nil }
    let fields = text.split(separator: ":", omittingEmptySubsequences: false)
    guard fields.count >= 4, let version = Int(fields[2]),
          version > 0, version <= 999_999_999 else { return nil }
    return version
  }

  // Read only bounded, regular, unsymlinked local CVD/CLD headers.
  private static func installedRevision(_ name: String, in directory: URL) -> Int? {
    for suffix in [".cld", ".cvd"] {
      let path = directory.appendingPathComponent(name + suffix).path
      let fd = open(path, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC)
      guard fd >= 0 else { continue }
      defer { close(fd) }
      var metadata = stat()
      guard fstat(fd, &metadata) == 0,
            (metadata.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else {
        return nil
      }
      var bytes = [UInt8](repeating: 0, count: 512)
      let count = bytes.withUnsafeMutableBytes {
        Darwin.read(fd, $0.baseAddress, $0.count)
      }
      guard count > 0 else { return nil }
      return databaseRevision(header: Data(bytes.prefix(Int(count))))
    }
    return nil
  }

  static func checkSignatureUpdates() async -> String {
    await Task.detached(priority: .userInitiated) {
      // ClamAV publishes main and daily revisions in this DNS TXT record.
      // Do not run FreshClam here: it downloads and modifies the database.
      let process = Process()
      process.executableURL = URL(fileURLWithPath: "/usr/bin/dig")
      process.arguments = ["+short", "+time=3", "+tries=1", "TXT", "current.cvd.clamav.net"]
      let output = Pipe()
      process.standardOutput = output
      process.standardError = FileHandle.nullDevice
      do {
        try process.run()
        let data = output.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        guard process.terminationReason == .exit, process.terminationStatus == 0,
              data.count <= 512, let answer = String(data: data, encoding: .utf8),
              let published = publishedRevisions(from: answer) else {
          return "Could not verify published ClamAV signature revisions."
        }
        let directory = FileManager.default.homeDirectoryForCurrentUser
          .appendingPathComponent("Library/Application Support/Studio/allow-and-open/signatures")
        guard let main = installedRevision("main", in: directory),
              let daily = installedRevision("daily", in: directory) else {
          return "Installed signature database versions unavailable for comparison."
        }
        if published.main > main || published.daily > daily {
          return "Newer ClamAV signatures are advertised. Choose Update Signatures Now to install them."
        }
        return "No newer signature revisions were advertised. Scanner freshness checks still apply."
      } catch {
        return "Could not check ClamAV signature updates."
      }
    }.value
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
