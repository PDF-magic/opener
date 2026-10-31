import AppKit
import Foundation

@main
struct TestFirstRunBrowsers {
  static func main() throws {
    let manager = FileManager.default
    let root = manager.temporaryDirectory
      .appendingPathComponent("first-run-browser-detection-" + UUID().uuidString, isDirectory: true)
    try manager.createDirectory(at: root, withIntermediateDirectories: true)
    defer { try? manager.removeItem(at: root) }
    let launchMarker = root.appendingPathComponent("unexpected-browser-launch")

    func fixture(_ name: String, id: String, executable: Bool = true) throws -> URL {
      let app = root.appendingPathComponent(name + ".app", isDirectory: true)
      let macOS = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
      try manager.createDirectory(at: macOS, withIntermediateDirectories: true)
      let plist = try PropertyListSerialization.data(
        fromPropertyList: [
          "CFBundleIdentifier": id,
          "CFBundleExecutable": "Browser",
          "CFBundlePackageType": "APPL",
        ], format: .xml, options: 0)
      try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
      if executable {
        let program = macOS.appendingPathComponent("Browser")
        try "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
          .write(to: program, atomically: true, encoding: .utf8)
        try manager.setAttributes([.posixPermissions: 0o755], ofItemAtPath: program.path)
      }
      return app
    }

    let brave = try fixture("Brave", id: "com.brave.Browser")
    let firefox = try fixture("Firefox", id: "org.mozilla.firefox")
    let safari = try fixture("Safari", id: "com.apple.Safari")
    let fakeChrome = try fixture("Chrome Impostor", id: "com.google.Chrome.fake")
    let brokenEdge = try fixture("Broken Edge", id: "com.microsoft.edgemac", executable: false)
    let unrelated = try fixture("Editor", id: "example.editor")
    let absent = root.appendingPathComponent("Missing.app", isDirectory: true)

    var queried = Set<String>()
    let browsers = DefaultPDFBrowserPreferences.discover(
      lookup: { identifier in
        queried.insert(identifier)
        switch identifier {
        case "com.brave.Browser": return [brave, brave]
        case "org.mozilla.firefox": return [firefox]
        case "com.apple.Safari": return [safari]
        case "com.google.Chrome": return [fakeChrome, unrelated]
        case "com.microsoft.edgemac": return [brokenEdge, absent]
        default: return []
        }
      },
      isExecutable: { manager.isExecutableFile(atPath: $0) }
    )
    precondition(browsers.map(\.name) == ["Brave", "Firefox", "Safari"])
    precondition(browsers.map(\.id) == [
      "com.brave.Browser", "org.mozilla.firefox", "com.apple.Safari"
    ])
    precondition(browsers.map(\.applicationURL) == [brave, firefox, safari])
    precondition(queried == Set(DefaultPDFBrowserPreferences.monitoringBrowserCatalog.map(\.id)))
    precondition(!manager.fileExists(atPath: launchMarker.path),
                 "First-run browser inventory must never launch a browser")

    let empty = DefaultPDFBrowserPreferences.discover(
      lookup: { _ in [] }, isExecutable: { _ in false }
    )
    precondition(empty.isEmpty, "No registered browsers must produce a true empty result")
    precondition(!manager.fileExists(atPath: launchMarker.path))
    print("First-run supported browser detection and read-only isolation passed")
  }
}
