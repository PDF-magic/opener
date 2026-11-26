import Foundation

@main
struct TestInitialConfiguration {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.initial-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Could not create isolated test defaults")
    }
    defer { defaults.removePersistentDomain(forName: suite) }
    let progress = ScanProgressPreference.key
    let success = SuccessfulScanNotificationPreference.key
    let blocked = BlockedFileNotificationPreference.key

    precondition(defaults.object(forKey: progress) == nil)
    precondition(defaults.object(forKey: success) == nil)
    precondition(defaults.object(forKey: blocked) == nil)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.object(forKey: progress) as? Bool == true)
    precondition(defaults.object(forKey: success) as? Bool == false)
    precondition(defaults.object(forKey: blocked) as? Bool == false)
    precondition(defaults.dictionaryRepresentation()[progress] as? Bool == true)

    defaults.set(false, forKey: progress)
    defaults.set(true, forKey: success)
    defaults.set(true, forKey: blocked)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.object(forKey: progress) as? Bool == false)
    precondition(defaults.object(forKey: success) as? Bool == true)
    precondition(defaults.object(forKey: blocked) as? Bool == true)

    defaults.removeObject(forKey: progress)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    precondition(defaults.object(forKey: progress) as? Bool == true)
    precondition(defaults.object(forKey: success) as? Bool == true)
    precondition(!InitialConfiguration.createIfNeeded(defaults: nil))
    print("Initial configuration creation tests passed")
  }
}
