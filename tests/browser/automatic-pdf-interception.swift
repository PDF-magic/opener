import Foundation
import CoreFoundation

// A disposable suite: no real user preference, permission or browser changes.
@main
struct TestBrowserAutomaticPDFInterception {
  static func main() {
    let suite = "local.studio.pdf-magic-opener.interception-test.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      fatalError("Missing isolated defaults")
    }
    defer { defaults.removePersistentDomain(forName: suite) }

    let pref = BrowserAutomaticPDFInterceptionPreference.self
    let chrome = "com.google.Chrome"
    let edge = "com.microsoft.edgemac"
    let firefox = "org.mozilla.firefox"
    let unsupported = ["com.apple.Safari", "com.brave.Browser", "org.chromium.Chromium",
                       "com.vivaldi.Vivaldi", "com.operasoftware.Opera",
                       "company.thebrowser.Browser", "custom.browser", ""]

    assert(pref.candidateBrowserIDs == Set([chrome, edge, firefox]))
    assert(pref.eligibleBrowserIDs(installedIDs: Set([chrome, firefox, unsupported[0]])) ==
           Set([chrome, firefox]))
    assert(pref.eligibleBrowserIDs(installedIDs: Set(unsupported)).isEmpty)
    assert(pref.eligibleBrowserIDs(installedIDs: []).isEmpty)
    assert(!pref.isOptedIn(for: chrome, defaults: defaults))
    assert(defaults.object(forKey: pref.key) == nil)

    for id in unsupported {
      assert(!pref.saveOptIn(true, for: id, defaults: defaults))
      assert(!pref.isOptedIn(for: id, defaults: defaults))
    }
    assert(defaults.object(forKey: pref.key) == nil)

    defaults.set(["com.google.Chrome": 1], forKey: pref.key)
    assert(!pref.isOptedIn(for: chrome, defaults: defaults))
    defaults.set(["com.google.Chrome": "true"], forKey: pref.key)
    assert(!pref.isOptedIn(for: chrome, defaults: defaults))
    defaults.removeObject(forKey: pref.key)

    defaults.set("preserve me", forKey: "customUserChoice")
    assert(pref.saveOptIn(true, for: chrome, defaults: defaults))
    assert(pref.saveOptIn(true, for: firefox, defaults: defaults))
    assert(pref.isOptedIn(for: chrome, defaults: defaults))
    assert(pref.isOptedIn(for: firefox, defaults: defaults))
    assert(!pref.isOptedIn(for: edge, defaults: defaults))
    assert(pref.isOptedIn(for: chrome, defaults: UserDefaults(suiteName: suite)))
    assert(pref.saveOptIn(false, for: chrome, defaults: defaults))
    assert(!pref.isOptedIn(for: chrome, defaults: defaults))
    assert(pref.isOptedIn(for: firefox, defaults: defaults))
    assert(defaults.string(forKey: "customUserChoice") == "preserve me")

    defaults.set("unexpected future format", forKey: pref.key)
    assert(!pref.saveOptIn(true, for: edge, defaults: defaults))
    assert(defaults.string(forKey: pref.key) == "unexpected future format")
    assert(!pref.saveOptIn(true, for: edge, defaults: nil))
    print("PASS: automatic PDF interception preference remains browser-gated and inactive")
  }
}
