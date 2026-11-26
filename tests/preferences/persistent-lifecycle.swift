import Foundation

// Exercise the real shared UserDefaults suite across separate processes. A
// replacement executable at another path simulates an app upgrade while the
// user's persistent preferences domain remains unchanged.
@main
struct PersistentSettingsLifecycleTests {
  private static func verify(_ suite: String, marker: String) {
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot reopen isolated preferences domain")
    }
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(!ScanProgressPreference.isEnabled(defaults: defaults))
    precondition(SuccessfulScanNotificationPreference.isEnabled(defaults: defaults))
    precondition(BlockedFileNotificationPreference.isEnabled(defaults: defaults))
    precondition(defaults.string(forKey: "unrelatedPreference") == marker)
    precondition(defaults.string(forKey: "futureSetting") == "keep-existing")
  }

  private static func run(_ executable: URL, suite: String, marker: String) throws {
    let process = Process()
    process.executableURL = executable
    process.arguments = ["--relaunch", suite, marker]
    try process.run()
    process.waitUntilExit()
    precondition(process.terminationReason == .exit && process.terminationStatus == 0)
  }

  static func main() throws {
    let arguments = CommandLine.arguments
    if arguments.count == 4 && arguments[1] == "--relaunch" {
      verify(arguments[2], marker: arguments[3])
      return
    }
    precondition(arguments.count == 1)

    let suite = "local.studio.pdf-magic-opener.lifecycle-test.\(UUID().uuidString)"
    let marker = UUID().uuidString
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot create isolated preferences domain")
    }
    defer {
      defaults.removePersistentDomain(forName: suite)
      _ = defaults.synchronize()
    }

    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    defaults.set(false, forKey: ScanProgressPreference.key)
    defaults.set(true, forKey: SuccessfulScanNotificationPreference.key)
    defaults.set(true, forKey: BlockedFileNotificationPreference.key)
    defaults.set(marker, forKey: "unrelatedPreference")
    defaults.set("keep-existing", forKey: "futureSetting")
    precondition(defaults.synchronize())

    let executable = URL(fileURLWithPath: arguments[0]).standardizedFileURL
    try run(executable, suite: suite, marker: marker) // App restart.

    let updateDirectory = FileManager.default.temporaryDirectory
      .appendingPathComponent("pdf-magic-upgrade-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(at: updateDirectory, withIntermediateDirectories: false)
    defer { try? FileManager.default.removeItem(at: updateDirectory) }
    let replacement = updateDirectory.appendingPathComponent("UpdatedPDFMagicOpener")
    try FileManager.default.copyItem(at: executable, to: replacement)
    try run(replacement, suite: suite, marker: marker) // Updated app binary.

    verify(suite, marker: marker)
    print("Settings survive relaunch and replacement binary without resetting customizations")
  }
}
