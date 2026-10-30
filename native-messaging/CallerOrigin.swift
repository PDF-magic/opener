import Foundation

// Defense in depth for browser launch metadata; NOT caller/process authentication.
// A local process can forge argv. This never authorizes a scan or PDF opening.
enum NativeCallerOrigin {
  enum Admission: Equatable {
    case localTransportOnly
    case registeredExtension
    case denied
  }

  private static let hostName = "org.pdfmagic.opener"
  private static let maxManifestBytes = 65_536
  // Opera uses Chrome's location; Chrome for Testing 146+ uses ChromeForTesting.
  private static let chromiumLocations = [
    "Google/Chrome", "Google/ChromeForTesting", "Chromium",
    "Microsoft Edge", "BraveSoftware/Brave-Browser", "Vivaldi", "Arc/User Data"
  ]
  private static let firefoxLocations = [
    "Library/Application Support/Mozilla/NativeMessagingHosts",
    ".mozilla/native-messaging-hosts"
  ]

  private static func validChromeID(_ id: String) -> Bool {
    let bytes = Array(id.utf8)
    return bytes.count == 32 && bytes.allSatisfy { (97...112).contains($0) }
  }

  private static func validFirefoxID(_ id: String) -> Bool {
    let bytes = Array(id.utf8)
    return !bytes.isEmpty && bytes.count <= 255 && bytes.allSatisfy {
      (65...90).contains($0) || (97...122).contains($0) ||
      (48...57).contains($0) || [45, 46, 64, 95, 123, 125, 43].contains($0)
    } && !id.contains("*") && !id.contains("..") &&
      (id.contains("@") || (id.first == "{" && id.last == "}"))
  }

  private static func chromiumOrigin(_ raw: String) -> String? {
    let prefix = "chrome-extension://"
    guard raw.hasPrefix(prefix) else { return nil }
    let remainder = String(raw.dropFirst(prefix.count))
    let id = remainder.hasSuffix("/") ? String(remainder.dropLast()) : remainder
    guard validChromeID(id) else { return nil }
    return prefix + id + "/"
  }

  private static func isSafeFile(_ path: String) -> Bool {
    guard path.hasPrefix("/"),
          URL(fileURLWithPath: path).standardizedFileURL.path == path,
          let attrs = try? FileManager.default.attributesOfItem(atPath: path),
          (attrs[.type] as? FileAttributeType) == .typeRegular else { return false }
    return true
  }

  private static func isSafePath(_ file: URL, home: URL) -> Bool {
    let homePath = home.standardizedFileURL.path
    let filePath = file.standardizedFileURL.path
    guard filePath.hasPrefix(homePath + "/"), file.path == filePath,
          let homeAttrs = try? FileManager.default.attributesOfItem(atPath: homePath),
          (homeAttrs[.type] as? FileAttributeType) == .typeDirectory else {
      return false
    }
    // macOS can represent system ancestors via /var -> /private/var.
    // Reject links from the selected user home downward; never follow an
    // untrusted registration-directory component or manifest symlink.
    var current = homePath
    for segment in filePath.dropFirst(homePath.count + 1).split(separator: "/") {
      current += "/" + segment
      guard let attrs = try? FileManager.default.attributesOfItem(atPath: current),
            let kind = attrs[.type] as? FileAttributeType,
            kind != .typeSymbolicLink else { return false }
    }
    return isSafeFile(filePath)
  }

  private static func manifestAllows(
    _ path: URL, home: URL, executable: String, approvedValue: String,
    firefox: Bool
  ) -> Bool {
    guard isSafePath(path, home: home),
          let attrs = try? FileManager.default.attributesOfItem(atPath: path.path),
          let size = attrs[.size] as? NSNumber,
          size.intValue > 0 && size.intValue <= maxManifestBytes,
          let bytes = try? Data(contentsOf: path), bytes.count <= maxManifestBytes,
          let object = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
          Set(object.keys) == ["name", "description", "path", "type",
                               firefox ? "allowed_extensions" : "allowed_origins"],
          object["name"] as? String == hostName, object["type"] as? String == "stdio",
          let description = object["description"] as? String, !description.isEmpty,
          let executableInManifest = object["path"] as? String,
          executableInManifest == executable,
          isSafeFile(executableInManifest),
          FileManager.default.isExecutableFile(atPath: executableInManifest),
          let allowed = object[firefox ? "allowed_extensions" : "allowed_origins"] as? [String],
          !allowed.isEmpty && allowed.count <= 32 &&
          Set(allowed).count == allowed.count else { return false }
    guard allowed.allSatisfy({
      firefox ? validFirefoxID($0) : chromiumOrigin($0) == $0
    }) else { return false }
    return allowed.contains(approvedValue)
  }

  static func verify(arguments: [String], home: URL, executable: String) -> Admission {
    // Retain existing local transport-only probes. They never grant privileges.
    if arguments.count == 1 { return .localTransportOnly }
    guard isSafeFile(executable),
          FileManager.default.isExecutableFile(atPath: executable) else { return .denied }
    let manifestName = hostName + ".json"
    if arguments.count == 2, let origin = chromiumOrigin(arguments[1]) {
      for location in chromiumLocations {
        let path = home.appendingPathComponent("Library/Application Support/" + location)
          .appendingPathComponent("NativeMessagingHosts/" + manifestName)
        if manifestAllows(path, home: home, executable: executable,
                          approvedValue: origin, firefox: false) {
          return .registeredExtension
        }
      }
    }
    // Firefox supplies (manifest-path, Gecko extension ID), not a Chrome origin.
    if arguments.count == 3, validFirefoxID(arguments[2]) {
      for location in firefoxLocations {
        let path = home.appendingPathComponent(location).appendingPathComponent(manifestName)
        if arguments[1] == path.path &&
            manifestAllows(path, home: home, executable: executable,
                           approvedValue: arguments[2], firefox: true) {
          return .registeredExtension
        }
      }
    }
    return .denied
  }

  static func verifyProcessArguments() -> Admission {
    guard let executable = Bundle.main.executableURL?.standardizedFileURL.path else {
      return .denied
    }
    return verify(arguments: CommandLine.arguments,
                  home: FileManager.default.homeDirectoryForCurrentUser,
                  executable: executable)
  }
}
