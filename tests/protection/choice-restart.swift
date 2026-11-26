import Darwin
import Foundation

// opener-0336: save each planned tier immediately and verify it in a real
// restarted process. The installed scanner remains Built-in throughout.
@main
struct ProtectionChoiceRestartTests {
  static func suite(_ label: String) -> (String, UserDefaults) {
    let name = "local.studio.pdf-magic-opener.preview-restart.\(label).\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: name) else { fatalError("Missing test suite") }
    return (name, defaults)
  }

  static func checkRestart(_ name: String, expected: PreferredProtectionLevel?) throws {
    let child = Process()
    child.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
    child.arguments = ["--reopened", name, expected?.rawValue ?? "unassigned"]
    try child.run()
    child.waitUntilExit()
    precondition(child.terminationStatus == 0, "Restart did not restore the saved preview choice")
  }

  static func main() throws {
    if CommandLine.arguments.count == 4, CommandLine.arguments[1] == "--reopened" {
      guard let defaults = UserDefaults(suiteName: CommandLine.arguments[2]),
            defaults.synchronize() else { exit(2) }
      let expected = CommandLine.arguments[3]
      if PlannedProtectionLevelPreference.selected(defaults: defaults)?.rawValue !=
          (expected == "unassigned" ? nil : expected) { exit(3) }
      if SelectedProtectionProfilePreference.selected(defaults: defaults) != .builtIn { exit(4) }
      if defaults.string(forKey: "customViewer") != "com.example.unchanged" { exit(5) }
      exit(0)
    }

    let (name, defaults) = suite("fresh")
    defer { defaults.removePersistentDomain(forName: name) }
    defaults.set("com.example.unchanged", forKey: "customViewer")
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == nil)
    precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn)
    try checkRestart(name, expected: nil)

    for preferred: PreferredProtectionLevel in [.enhanced, .maximum, .standard] {
      precondition(PlannedProtectionLevelPreference.saveExplicitChoice(preferred, defaults: defaults))
      precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == preferred)
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      try checkRestart(name, expected: preferred)
      precondition(defaults.string(forKey: "customViewer") == "com.example.unchanged")
      precondition(defaults.string(forKey: SelectedProtectionProfilePreference.key) == "built-in")
    }

    // General preference reset must not clear the explicit preview choice.
    precondition(GeneralPreferencesReset.reset(defaults: defaults))
    try checkRestart(name, expected: .standard)

    // A future or malformed stored tier must not be silently mapped to a
    // preview or overwritten on launch.
    defaults.set("future-level", forKey: PlannedProtectionLevelPreference.key)
    precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == nil)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.string(forKey: PlannedProtectionLevelPreference.key) == "future-level")

    // Failed or invalid writes cannot mutate the saved choice or scanner.
    defaults.set(2, forKey: ActiveConfigurationSchemaVersion.key)
    precondition(!PlannedProtectionLevelPreference.saveExplicitChoice(.maximum, defaults: defaults))
    precondition(defaults.string(forKey: PlannedProtectionLevelPreference.key) == "future-level")
    precondition(!PlannedProtectionLevelPreference.saveExplicitChoice(.enhanced, defaults: nil))
    precondition(SelectedProtectionProfilePreference.selected(defaults: defaults) == .builtIn)
    precondition(defaults.string(forKey: "customViewer") == "com.example.unchanged")

    // A recognized prior install retains Standard unless explicitly changed.
    let (oldName, oldDefaults) = suite("legacy")
    defer { oldDefaults.removePersistentDomain(forName: oldName) }
    oldDefaults.set("com.example.unchanged", forKey: "customViewer")
    oldDefaults.set(1, forKey: ActiveConfigurationSchemaVersion.key)
    oldDefaults.set("built-in", forKey: SelectedProtectionProfilePreference.key)
    precondition(InitialConfiguration.createIfNeeded(defaults: oldDefaults))
    precondition(PlannedProtectionLevelPreference.selected(defaults: oldDefaults) == .standard)
    try checkRestart(oldName, expected: .standard)
    print("Protection preview choices persist across actual process restarts")
  }
}
