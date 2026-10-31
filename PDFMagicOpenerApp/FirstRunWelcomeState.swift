import Foundation

// This is a presentation-only acknowledgement, separate from all scanner,
// PDF target, macOS file association, and existing preferences configuration.
enum FirstRunWelcomeState {
  static let acknowledgementKey = "firstRunWelcomeAcknowledged.v1"

  static func shouldShow(defaults: UserDefaults = .standard) -> Bool {
    defaults.object(forKey: acknowledgementKey) as? Bool != true
  }

  // Only the user's explicit Continue action records completion. Opening,
  // closing, or abandoning the welcome does not silently mark it complete.
  static func acknowledge(defaults: UserDefaults = .standard) {
    defaults.set(true, forKey: acknowledgementKey)
  }
}
