import Foundation

// Each child reads the same isolated suite in a separate macOS process.
@main
struct TestCrossProcessEffectiveConfiguration {
  static func effective(_ defaults: UserDefaults?) -> String {
    let value = EffectivePresentationConfiguration.read(defaults: defaults)
    return "\(value.showScanProgress),\(value.showSuccessfulScanNotifications),\(value.showBlockedFileNotifications)"
  }

  static func child(_ command: String, suiteName: String) -> String {
    let process = Process()
    process.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
    process.arguments = [command, suiteName]
    let output = Pipe()
    process.standardOutput = output
    try! process.run()
    let data = output.fileHandleForReading.readDataToEndOfFile()
    process.waitUntilExit()
    precondition(process.terminationReason == .exit && process.terminationStatus == 0)
    return String(decoding: data, as: UTF8.self).trimmingCharacters(in: .whitespacesAndNewlines)
  }

  static func main() {
    let args = CommandLine.arguments
    if args.count == 3 {
      guard let defaults = UserDefaults(suiteName: args[2]) else { fatalError("Missing test suite") }
      switch args[1] {
      case "read":
        print(effective(defaults))
      case "write":
        defaults.set(true, forKey: ScanProgressPreference.key)
        defaults.set(false, forKey: SuccessfulScanNotificationPreference.key)
        defaults.set(true, forKey: BlockedFileNotificationPreference.key)
        precondition(defaults.synchronize())
        print(effective(defaults))
      default:
        fatalError("Unexpected test command")
      }
      return
    }

    let suiteName = "local.studio.pdf-magic-opener.cross-process.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suiteName) else { fatalError("Missing test suite") }
    defer { defaults.removePersistentDomain(forName: suiteName) }

    precondition(effective(defaults) == "true,false,false", "Legacy defaults must match")
    precondition(child("read", suiteName: suiteName) == "true,false,false")
    defaults.set("preserved", forKey: "unrelatedCustomization")
    precondition(ScanProgressPreference.save(false, defaults: defaults))
    precondition(SuccessfulScanNotificationPreference.save(true, defaults: defaults))
    precondition(BlockedFileNotificationPreference.save(false, defaults: defaults))
    precondition(child("read", suiteName: suiteName) == "false,true,false",
                 "A new handler must see settings saved by the UI")
    precondition(child("write", suiteName: suiteName) == "true,false,true")
    precondition(effective(defaults) == "true,false,true",
                 "An existing process must refresh effective preferences")
    precondition(child("read", suiteName: suiteName) == "true,false,true")
    precondition(defaults.string(forKey: "unrelatedCustomization") == "preserved")
    precondition(effective(nil) == "true,false,false", "Unavailable suite must fail safely")
    print("Cross-process effective configuration tests passed")
  }
}
