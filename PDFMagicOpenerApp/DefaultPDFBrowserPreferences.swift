import AppKit
import Darwin
import Foundation

// A browser selection always goes through the *installed* validated chooser.
// Never write target-app.txt directly from the SwiftUI app or assume that
// an installed bundle is safe to open PDFs without the existing verifier.
struct PDFBrowserOption: Identifiable {
  let id: String
  let name: String
  let applicationURL: URL
}

enum DefaultPDFBrowserPreferences {
  private static let browserNames: [(String, String)] = [
    ("com.brave.Browser", "Brave"),
    ("com.google.Chrome", "Google Chrome"),
    ("org.chromium.Chromium", "Chromium"),
    ("com.microsoft.edgemac", "Microsoft Edge"),
    ("com.vivaldi.Vivaldi", "Vivaldi"),
    ("com.operasoftware.Opera", "Opera"),
    ("company.thebrowser.Browser", "Arc"),
    ("org.mozilla.firefox", "Firefox"),
    ("com.apple.Safari", "Safari"),
  ]

  // Stable, read-only supported-browser roster for status presentation.
  // Actual installation detection still uses the validated discover() path.
  static var monitoringBrowserCatalog: [(id: String, name: String)] {
    browserNames.map { (id: $0.0, name: $0.1) }
  }

  private static let preferenceDirectory = FileManager.default.homeDirectoryForCurrentUser
    .appendingPathComponent("Library/Application Support/Studio/allow-and-open", isDirectory: true)

  static func discover(
    lookup: (String) -> [URL] = {
      NSWorkspace.shared.urlsForApplications(withBundleIdentifier: $0)
    },
    isExecutable: (String) -> Bool = { FileManager.default.isExecutableFile(atPath: $0) }
  ) -> [PDFBrowserOption] {
    browserNames.compactMap { identifier, name in
      // Use only installed, registered and executable bundles. The existing
      // verifier must independently approve the exact choice before saving.
      for candidate in lookup(identifier) where candidate.isFileURL {
        let app = candidate.standardizedFileURL.resolvingSymlinksInPath()
        guard app.pathExtension.lowercased() == "app",
              let bundle = Bundle(url: app),
              bundle.bundleIdentifier == identifier,
              let executable = bundle.executableURL,
              isExecutable(executable.path) else { continue }
        return PDFBrowserOption(id: identifier, name: name, applicationURL: app)
      }
      return nil
    }
    .sorted { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }
  }

  // Read the same preference as the scanner, without following the configured
  // file symlink. Missing settings retain the historical Brave default.
  // Corrupt or unreadable settings never reset to a different browser.
  static func currentSelection() -> String? {
    let parentFD = open(preferenceDirectory.path, O_RDONLY | O_DIRECTORY | O_NOFOLLOW)
    guard parentFD >= 0 else { return errno == ENOENT ? SupportedPreferenceDefaults.pdfBrowserBundleIdentifier : nil }
    defer { close(parentFD) }

    let fileFD = openat(parentFD, "target-app.txt", O_RDONLY | O_NOFOLLOW)
    guard fileFD >= 0 else { return errno == ENOENT ? SupportedPreferenceDefaults.pdfBrowserBundleIdentifier : nil }
    defer { close(fileFD) }

    var info = stat()
    guard fstat(fileFD, &info) == 0,
          (info.st_mode & mode_t(S_IFMT)) == mode_t(S_IFREG) else { return nil }

    var bytes = [UInt8](repeating: 0, count: 257)
    let count = read(fileFD, &bytes, bytes.count)
    guard count > 0 && count <= 256,
          let text = String(bytes: bytes.prefix(count), encoding: .ascii) else { return nil }
    let identifier = text.trimmingCharacters(in: .whitespacesAndNewlines)
    if identifier == "system-default-browser" { return identifier }
    guard identifier.count <= 255,
          identifier.range(of: "^[A-Za-z0-9][A-Za-z0-9.-]{1,254}$",
                           options: .regularExpression) != nil,
          identifier.contains("."), !identifier.contains(".."),
          identifier != "local.studio.brave-pdf-opener" else { return nil }
    return identifier
  }

  static func saveVerified(_ option: PDFBrowserOption) -> Bool {
    // The installed chooser performs two independent PDF-capability checks,
    // then an atomic, no-symlink update. Do not duplicate that write here.
    let script = preferenceDirectory.appendingPathComponent("select-custom-pdf-application.py")
    guard let values = try? script.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey]),
          values.isRegularFile == true, values.isSymbolicLink != true else { return false }
    let process = Process()
    process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
    process.arguments = [script.path, "--application", option.applicationURL.path]
    process.standardOutput = Pipe()
    process.standardError = Pipe()
    do {
      try process.run()
      process.waitUntilExit()
      return process.terminationReason == .exit && process.terminationStatus == 0
    } catch {
      return false
    }
  }
}
