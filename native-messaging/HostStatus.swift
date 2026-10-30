import Foundation
#if canImport(AppKit)
import AppKit
#endif

// Read-only handshake metadata. This is not a scan verdict, permission grant,
// caller authentication, or a way to choose a protection profile.
enum NativeHostStatus {
  static let protocolVersion = 1
  static let applicationBundleIdentifier = "local.studio.pdfmagicopener.swiftui"
  static let preferencesSuite = "local.studio.pdf-magic-opener"
  static let selectedProfileKey = "selectedProtectionProfile"
  static let enforcedProfile = "built-in"

  static func applicationVersion(at bundleURL: URL?) -> String? {
    guard let bundleURL, bundleURL.isFileURL,
          bundleURL.pathExtension == "app",
          let bundle = Bundle(url: bundleURL),
          bundle.bundleIdentifier == applicationBundleIdentifier,
          let version = bundle.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String,
          !version.isEmpty, version.utf8.count <= 64,
          version.utf8.allSatisfy({ byte in
            (byte >= 48 && byte <= 57) || (byte >= 65 && byte <= 90) ||
            (byte >= 97 && byte <= 122) || byte == 46 || byte == 45 || byte == 43
          }) else {
      return nil
    }
    return version
  }

  // Only Built-in is an enforceable profile today. Missing saved preferences
  // use the existing default; unsupported stored values must not be reported
  // as an active selectable protection tier.
  static func effectiveProfile(from savedSelection: Any?) -> String? {
    guard let savedSelection else { return enforcedProfile }
    guard let value = savedSelection as? String,
          value == enforcedProfile else { return nil }
    return enforcedProfile
  }

  static func snapshot(appURL: URL?, savedSelection: Any?, preferencesAvailable: Bool = true)
    -> [String: Any] {
    let installedVersion = applicationVersion(at: appURL)
    let profile = preferencesAvailable ? effectiveProfile(from: savedSelection) : nil
    return [
      "applicationVersion": installedVersion ?? NSNull() as Any,
      "protocolVersion": protocolVersion,
      "activeProtectionProfile": profile ?? NSNull() as Any,
      "status": "transport-only",
      "scanAvailable": false
    ]
  }

  static func current() -> [String: Any] {
    // Resolve the registered SwiftUI application, never the standalone host
    // executable or the Safari extension's unrelated version.
    #if canImport(AppKit)
    let installedURL = NSWorkspace.shared.urlForApplication(
      withBundleIdentifier: applicationBundleIdentifier
    )
    #else
    let installedURL: URL? = nil
    #endif
    let defaults = UserDefaults(suiteName: preferencesSuite)
    return snapshot(
      appURL: installedURL,
      savedSelection: defaults?.object(forKey: selectedProfileKey),
      preferencesAvailable: defaults != nil
    )
  }
}
