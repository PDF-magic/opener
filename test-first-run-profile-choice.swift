import Foundation

@main
struct TestFirstRunProfileChoice {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.welcome-profile-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Cannot create isolated protection choice suite")
    }
    defaults.removePersistentDomain(forName: suite)
    defer { defaults.removePersistentDomain(forName: suite) }

    defaults.set("org.mozilla.firefox", forKey: "customPDFBrowser")
    defaults.set(false, forKey: ScanProgressPreference.key)
    precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
    let originalProfile = defaults.string(forKey: SelectedProtectionProfilePreference.key)
    precondition(originalProfile == "built-in")
    precondition(defaults.string(forKey: PlannedProtectionLevelPreference.key) ==
                 PlannedProtectionLevelPreference.newInstallationMarker)

    // Simply opening onboarding or continuing without a choice cannot write.
    precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == nil)
    precondition(!InitialProtectionProfileChoice.save(nil, defaults: defaults))
    precondition(defaults.string(forKey: PlannedProtectionLevelPreference.key) ==
                 PlannedProtectionLevelPreference.newInstallationMarker)

    for profile: PreferredProtectionLevel in [.standard, .enhanced, .maximum] {
      precondition(InitialProtectionProfileChoice.save(profile, defaults: defaults))
      guard let reopened = UserDefaults(suiteName: suite), reopened.synchronize() else {
        fatalError("Could not reopen preference suite")
      }
      precondition(PlannedProtectionLevelPreference.selected(defaults: reopened) == profile)
      precondition(reopened.string(forKey: SelectedProtectionProfilePreference.key) ==
                   originalProfile)
      precondition(reopened.string(forKey: "customPDFBrowser") == "org.mozilla.firefox")
      precondition(ScanProgressPreference.isEnabled(defaults: reopened) == false)
      precondition(InitialConfiguration.createIfNeeded(defaults: defaults))
      precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == profile)
    }

    // When configuration is unknown, do not overwrite the explicit preference.
    defaults.set("future-active-policy", forKey: SelectedProtectionProfilePreference.key)
    precondition(!InitialProtectionProfileChoice.save(.standard, defaults: defaults))
    precondition(PlannedProtectionLevelPreference.selected(defaults: defaults) == .maximum)
    precondition(defaults.string(forKey: SelectedProtectionProfilePreference.key) ==
                 "future-active-policy")
    precondition(defaults.string(forKey: "customPDFBrowser") == "org.mozilla.firefox")

    print("First-run protection choice tests passed")
  }
}
