import Foundation

@main
struct TestFirstRunScannerInstallation {
  static func main() throws {
    let files = FileManager.default
    let directory = files.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
    try files.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? files.removeItem(at: directory) }
    let first = directory.appendingPathComponent("arm", isDirectory: true)
    let second = directory.appendingPathComponent("intel", isDirectory: true)
    try files.createDirectory(at: first, withIntermediateDirectories: true)
    try files.createDirectory(at: second, withIntermediateDirectories: true)
    let clamscan = first.appendingPathComponent("clamscan")
    let freshclam = first.appendingPathComponent("freshclam")
    let alternative = second.appendingPathComponent("clamscan")
    let candidates = [clamscan.path, alternative.path]

    func makeFile(_ url: URL, executable: Bool = true) throws {
      guard files.createFile(atPath: url.path, contents: Data("test".utf8)) else {
        fatalError("Could not create test fixture")
      }
      try files.setAttributes([.posixPermissions: executable ? 0o755 : 0o644], ofItemAtPath: url.path)
    }

    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .scannerMissing)
    try makeFile(clamscan, executable: false)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .scannerMissing)
    try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: clamscan.path)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .updaterMissing)
    try makeFile(freshclam, executable: false)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .updaterMissing)
    try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: freshclam.path)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .detected)

    // Pair must be in the same prefix. Never fall back to another installation
    // when the first supported scanner has an incomplete updater.
    try files.removeItem(at: freshclam)
    try makeFile(second.appendingPathComponent("freshclam"))
    try makeFile(alternative)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .updaterMissing)
    try files.removeItem(at: clamscan)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .detected)

    // Homebrew-style symlink is accepted only for a real executable file.
    try files.removeItem(at: alternative)
    let target = directory.appendingPathComponent("real-clamscan")
    try makeFile(target)
    try files.createSymbolicLink(at: alternative, withDestinationURL: target)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .detected)
    try files.removeItem(at: target)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .scannerMissing)

    // A directory with a scanner filename cannot be mistaken for a binary.
    try files.removeItem(at: alternative)
    try files.createDirectory(at: alternative, withIntermediateDirectories: true)
    precondition(FirstRunScannerInstallation.check(candidates: candidates) == .scannerMissing)

    print("First-run read-only scanner installation tests passed")
  }
}
