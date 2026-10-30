import Foundation

@main
struct CallerOriginFixtures {
  static func main() throws {
    let root = FileManager.default.temporaryDirectory.resolvingSymlinksInPath()
      .appendingPathComponent(UUID().uuidString)
    let home = root.appendingPathComponent("home")
    try FileManager.default.createDirectory(at: home, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: root) }
    let executable = root.appendingPathComponent("native-host")
    try "#!/bin/sh\nexit 0\n".write(to: executable, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: executable.path)
    let chromeID = "abcdefghijklmnopabcdefghijklmnop"
    let origin = "chrome-extension://" + chromeID + "/"
    let chrome = home.appendingPathComponent("Library/Application Support/Google/Chrome/NativeMessagingHosts")
    try FileManager.default.createDirectory(at: chrome, withIntermediateDirectories: true)
    let chromeManifest = chrome.appendingPathComponent("org.pdfmagic.opener.json")
    func manifest(_ approved: [String], firefox: Bool = false) -> [String: Any] {
      return ["name": "org.pdfmagic.opener", "description": "transport only",
              "path": executable.path, "type": "stdio",
              firefox ? "allowed_extensions" : "allowed_origins": approved]
    }
    func write(_ fields: [String: Any], to path: URL) throws {
      try JSONSerialization.data(withJSONObject: fields).write(to: path)
    }
    func check(_ argv: [String], _ expected: NativeCallerOrigin.Admission, _ description: String) {
      let result = NativeCallerOrigin.verify(arguments: argv, home: home, executable: executable.path)
      precondition(result == expected, description + ": unexpected admission result")
    }
    check([executable.path], .localTransportOnly, "legacy unregistered transport")
    check([executable.path, origin], .denied, "missing registration")
    try write(manifest([origin]), to: chromeManifest)
    check([executable.path, origin], .registeredExtension, "approved chromium")
    check([executable.path, String(origin.dropLast())], .registeredExtension, "browser origin without slash")
    for invalid in [
      "chrome-extension://ponmlkjihgfedcbaponmlkjihgfedcba/",
      origin + "anything", "chrome-extension://" + chromeID.uppercased() + "/",
      origin + "?query", "https://" + chromeID, "*"
    ] {
      check([executable.path, invalid], .denied, "invalid/unapproved chromium")
    }
    check([executable.path, origin, "--parent-window=0"], .denied, "unsupported platform arguments")
    for invalid in [[origin, origin], ["chrome-extension://*/"], [origin, "http://example.com"]] {
      try write(manifest(invalid), to: chromeManifest)
      check([executable.path, origin], .denied, "invalid manifest allowlist")
    }
    try write(manifest([origin]), to: chromeManifest)
    let otherHost = root.appendingPathComponent("other-host")
    try "#!/bin/sh\nexit 0\n".write(to: otherHost, atomically: true, encoding: .utf8)
    try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: otherHost.path)
    try write(["name": "org.pdfmagic.opener", "description": "different binary",
               "path": otherHost.path, "type": "stdio", "allowed_origins": [origin]], to: chromeManifest)
    check([executable.path, origin], .denied, "different executable")
    try write(manifest([origin]), to: chromeManifest)
    try FileManager.default.removeItem(at: chromeManifest)
    try FileManager.default.createSymbolicLink(at: chromeManifest, withDestinationURL: otherHost)
    check([executable.path, origin], .denied, "symlink manifest")
    let firefoxID = "pdf-magic-opener@example.invalid"
    let firefox = home.appendingPathComponent("Library/Application Support/Mozilla/NativeMessagingHosts")
    try FileManager.default.createDirectory(at: firefox, withIntermediateDirectories: true)
    let firefoxManifest = firefox.appendingPathComponent("org.pdfmagic.opener.json")
    try write(manifest([firefoxID], firefox: true), to: firefoxManifest)
    check([executable.path, firefoxManifest.path, firefoxID], .registeredExtension, "approved Gecko extension")
    check([executable.path, firefoxManifest.path, "unapproved@example.com"], .denied, "unapproved Gecko ID")
    check([executable.path, firefoxManifest.path, "*"], .denied, "wildcard Gecko ID")
    check([executable.path, chromeManifest.path, firefoxID], .denied, "wrong manifest location")
    try write(manifest(["*@example.com"], firefox: true), to: firefoxManifest)
    check([executable.path, firefoxManifest.path, firefoxID], .denied, "Firefox wildcard manifest")
    try FileManager.default.removeItem(at: firefoxManifest)
    try FileManager.default.createSymbolicLink(at: firefoxManifest, withDestinationURL: otherHost)
    check([executable.path, firefoxManifest.path, firefoxID], .denied, "Firefox symlink manifest")
    print("Native caller-origin fixture checks passed")
  }
}
