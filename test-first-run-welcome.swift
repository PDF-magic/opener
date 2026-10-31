import Foundation

@main
struct TestFirstRunWelcome {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.welcome-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot initialize isolated welcome preferences")
    }
    defaults.removePersistentDomain(forName: suite)
    defer { defaults.removePersistentDomain(forName: suite) }

    let key = FirstRunWelcomeState.acknowledgementKey
    let customKey = "existingSelectedBrowser"
    defaults.set("org.mozilla.firefox", forKey: customKey)

    // Never write a marker merely because the welcome is displayed.
    precondition(defaults.object(forKey: key) == nil)
    precondition(FirstRunWelcomeState.shouldShow(defaults: defaults))
    precondition(FirstRunWelcomeState.shouldShow(defaults: defaults))
    precondition(defaults.object(forKey: key) == nil)

    // Only explicit acknowledgement dismisses this for future launches.
    FirstRunWelcomeState.acknowledge(defaults: defaults)
    precondition(defaults.object(forKey: key) as? Bool == true)
    precondition(!FirstRunWelcomeState.shouldShow(defaults: defaults))
    precondition(defaults.string(forKey: customKey) == "org.mozilla.firefox")
    FirstRunWelcomeState.acknowledge(defaults: defaults)
    precondition(!FirstRunWelcomeState.shouldShow(defaults: defaults))

    // This marker is independent of existing preferences and other defaults.
    defaults.set(false, forKey: key)
    precondition(FirstRunWelcomeState.shouldShow(defaults: defaults))
    defaults.removeObject(forKey: key)
    precondition(FirstRunWelcomeState.shouldShow(defaults: defaults))
    precondition(defaults.string(forKey: customKey) == "org.mozilla.firefox")

    print("First-run welcome acknowledgement tests passed")
  }
}
