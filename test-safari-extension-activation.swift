import Darwin
import Foundation
import SafariServices

// Read-only test harness: only the Safari user can enable or disable the extension.
private let safariExtensionIdentifier = "local.studio.pdfmagicopener.swiftui.safari"

private enum ExpectedActivation: String {
  case enabled
  case disabled
}

private func matches(_ expected: ExpectedActivation, observed: Bool?) -> Bool {
  guard let observed else { return false }
  return (expected == .enabled) == observed
}

@main
struct SafariExtensionActivationTest {
  static func main() {
    let arguments = Array(CommandLine.arguments.dropFirst())

    if arguments == ["--self-test"] {
      precondition(matches(.enabled, observed: true))
      precondition(matches(.disabled, observed: false))
      precondition(!matches(.enabled, observed: false))
      precondition(!matches(.disabled, observed: true))
      precondition(!matches(.enabled, observed: nil))
      precondition(!matches(.disabled, observed: nil))
      print("Safari activation expectations pass (no Safari preferences changed)")
      return
    }

    guard arguments.count == 2,
          arguments[0] == "--expect",
          let expected = ExpectedActivation(rawValue: arguments[1]) else {
      fputs("Usage: SafariExtensionActivationTest --self-test | --expect enabled|disabled\n", stderr)
      exit(64)
    }

    // This API reports Safari's state; it never enables an extension.
    // A missing/unregistered extension is NOT equivalent to disabled.
    SFSafariExtensionManager.getStateOfSafariExtension(
      withIdentifier: safariExtensionIdentifier
    ) { state, error in
      if let error {
        fputs("Safari extension state unavailable: \(error)\n", stderr)
        exit(2)
      }
      guard let state else {
        fputs("Safari extension not registered; install and launch the containing app first.\n", stderr)
        exit(2)
      }
      let observed = state.isEnabled ? "enabled" : "disabled"
      print("Safari extension \(safariExtensionIdentifier): \(observed)")
      exit(matches(expected, observed: state.isEnabled) ? 0 : 1)
    }

    // Fail closed rather than claiming a state when the API does not answer.
    DispatchQueue.main.asyncAfter(deadline: .now() + .seconds(10)) {
      fputs("Timed out waiting for Safari extension activation state.\n", stderr)
      exit(2)
    }
    RunLoop.main.run()
  }
}
