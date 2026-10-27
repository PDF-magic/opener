import AppKit

// Look up an installed macOS application by its bundle identifier, rather than
// assuming a particular Applications directory or a user-provided app path.
func resolveTargetApplication(
    bundleIdentifier: String,
    lookup: (String) -> URL? = { NSWorkspace.shared.urlForApplication(withBundleIdentifier: $0) }
) -> URL? {
    guard !bundleIdentifier.isEmpty,
          let app = lookup(bundleIdentifier)?.standardizedFileURL.resolvingSymlinksInPath(),
          app.pathExtension.lowercased() == "app" else {
        return nil
    }
    var directory: ObjCBool = false
    guard FileManager.default.fileExists(atPath: app.path, isDirectory: &directory),
          directory.boolValue,
          let bundle = Bundle(url: app),
          bundle.bundleIdentifier == bundleIdentifier,
          let executable = bundle.executableURL,
          FileManager.default.isExecutableFile(atPath: executable.path) else {
        return nil
    }
    return app
}

let arguments = CommandLine.arguments
guard arguments.count == 2,
      let application = resolveTargetApplication(bundleIdentifier: arguments[1]) else {
    fputs("Target application could not be resolved or is unavailable.\n", stderr)
    exit(1)
}
let payload = try JSONSerialization.data(withJSONObject: ["path": application.path])
FileHandle.standardOutput.write(payload)
FileHandle.standardOutput.write(Data([10]))
