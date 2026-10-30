import Foundation

// Defense-in-depth rejection at the stdio native-host boundary (opener-0654).
// Launch arguments can be forged by local processes: this is NOT authentication,
// and no native input is permitted to authorize a scan or PDF opening.
enum NativeCallerAdmission {
  private static let hostName = "org.pdfmagic.opener"
  private static let manifestName = hostName + ".json"
  private static let maxManifestBytes = 16 * 1024
  private static let maxApprovedIds = 32
  private static let chromiumDirectories = [
    "Google/Chrome", "Chromium", "Google/ChromeForTesting",
    "Microsoft Edge", "BraveSoftware/Brave-Browser", "Vivaldi", "Arc/User Data"
  ]

  private static func pathIsSafe(_ path: String, directory: Bool) -> Bool {
    guard path.hasPrefix("/"), !path.contains("/../"), !path.contains("/./") else {
      return false
    }
    // Walk every component: neither the manifest nor an ancestor may redirect
    // admission to a different user's file via a symbolic link.
    var current = ""
    for component in path.split(separator: "/") {
      current += "/" + component
      guard let info = try? FileManager.default.attributesOfItem(atPath: current),
            let kind = info[.type] as? FileAttributeType,
            kind != .typeSymbolicLink else { return false }
      if current != path && kind != .typeDirectory { return false }
      if current == path && kind != (directory ? .typeDirectory : .typeRegular) {
        return false
      }
    }
    return true
  }

  private static func chromiumOrigin(_ origin: String) -> Bool {
    let prefix = "chrome-extension://"
    guard origin.hasPrefix(prefix), origin.hasSuffix("/") else { return false }
    let id = String(origin.dropFirst(prefix.count).dropLast())
    return id.utf8.count == 32 && id.utf8.allSatisfy { (97...112).contains($0) }
  }

  private static func firefoxExtensionId(_ id: String) -> Bool {
    guard !id.isEmpty, id.utf8.count <= 320, !id.contains("/") else { return false }
    // Browser-owned Gecko ID format, including signed production IDs and
    // the already reviewed explicit development ID.
    let pattern = #"^(?:[A-Za-z0-9._+-]{1,64}@[A-Za-z0-9.-]{1,253}|\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\})$"#
    return id.range(of: pattern, options: .regularExpression) != nil
  }

  private static func manifestAllows(
    path: String, caller: String, firefox: Bool, executable: String
  ) -> Bool {
    guard pathIsSafe(path, directory: false),
          let size = (try? FileManager.default.attributesOfItem(atPath: path)[.size]) as? NSNumber,
          size.intValue > 0, size.intValue <= maxManifestBytes,
          let data = try? Data(contentsOf: URL(fileURLWithPath: path)),
          data.count <= maxManifestBytes,
          let manifest = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
      return false
    }
    let allowKey = firefox ? "allowed_extensions" : "allowed_origins"
    guard Set(manifest.keys) == Set([
      "name", "description", "path", "type", allowKey
    ]), manifest["name"] as? String == hostName,
    manifest["type"] as? String == "stdio",
    let description = manifest["description"] as? String, !description.isEmpty,
    description.utf8.count <= 256,
    let registeredExecutable = manifest["path"] as? String,
    registeredExecutable == executable,
    pathIsSafe(executable, directory: false),
    let approved = manifest[allowKey] as? [String],
    !approved.isEmpty, approved.count <= maxApprovedIds,
    Set(approved).count == approved.count,
    approved.allSatisfy({ firefox ? firefoxExtensionId($0) : chromiumOrigin($0) })
    else { return false }
    return approved.contains(caller)
  }

  static func allows(
    _ arguments: [String],
    home: String? = nil,
    executablePath: String? = nil
  ) -> Bool {
    guard let home = home ?? ProcessInfo.processInfo.environment["HOME"],
          pathIsSafe(home, directory: true),
          let executable = executablePath ?? Bundle.main.executableURL?.path,
          executable.hasPrefix("/"), pathIsSafe(executable, directory: false) else {
      return false
    }
    if arguments.count == 1 {
      let origin = arguments[0]
      guard chromiumOrigin(origin) else { return false }
      #if os(macOS)
      for directory in chromiumDirectories {
        let path = home + "/Library/Application Support/" + directory +
          "/NativeMessagingHosts/" + manifestName
        if manifestAllows(path: path, caller: origin, firefox: false,
                          executable: executable) { return true }
      }
      #endif
      return false
    }
    if arguments.count == 2 {
      let path = arguments[0], id = arguments[1]
      guard firefoxExtensionId(id) else { return false }
      #if os(macOS)
      let expected = home + "/Library/Application Support/Mozilla/NativeMessagingHosts/" +
        manifestName
      #elseif os(Linux)
      let expected = home + "/.mozilla/native-messaging-hosts/" + manifestName
      #else
      return false
      #endif
      return path == expected &&
        manifestAllows(path: expected, caller: id, firefox: true,
                       executable: executable)
    }
    return false
  }
}
