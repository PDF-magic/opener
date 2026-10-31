import Foundation

// First-run display diagnostic only. This does not authorize a scan or an open.
// The installed scan gate independently validates ClamAV and signature health.
enum FirstRunScannerInstallation {
  enum Status: Equatable {
    case detected
    case scannerMissing
    case updaterMissing
  }

  // Keep candidate order aligned with scan-and-open.py's runtime discovery.
  static let scannerCandidates = [
    "/opt/homebrew/bin/clamscan",
    "/usr/local/bin/clamscan",
    "/usr/local/clamav/bin/clamscan",
  ]

  static func check(candidates: [String] = scannerCandidates) -> Status {
    for scanner in candidates {
      guard isExecutableRegularFile(scanner) else { continue }
      let updater = URL(fileURLWithPath: scanner).deletingLastPathComponent()
        .appendingPathComponent("freshclam").path
      return isExecutableRegularFile(updater) ? .detected : .updaterMissing
    }
    return .scannerMissing
  }

  private static func isExecutableRegularFile(_ path: String) -> Bool {
    // Allow Homebrew binary symlinks only when they resolve to real executable
    // files. Do not run either binary, read user documents, or change settings.
    let resolved = URL(fileURLWithPath: path).resolvingSymlinksInPath().path
    let files = FileManager.default
    guard let attributes = try? files.attributesOfItem(atPath: resolved),
          attributes[.type] as? FileAttributeType == .typeRegular else { return false }
    return files.isExecutableFile(atPath: resolved)
  }
}
