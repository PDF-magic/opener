import AppKit
import Foundation

// opener-1058: multiple installed browsers must remain independent PDF targets.
// All applications and preferences are disposable; no Launch Services state,
// real browser, scanner, or document is modified or launched.
@main
struct MultipleBrowserInstallationsTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory.appendingPathComponent(
            "pdf-multiple-browsers-1058-" + UUID().uuidString, isDirectory: true)
        let system = root.appendingPathComponent("Applications", isDirectory: true)
        let userApps = root.appendingPathComponent("User/Applications", isDirectory: true)
        let custom = root.appendingPathComponent("External Apps", isDirectory: true)
        for directory in [system, userApps, custom] {
            try files.createDirectory(at: directory, withIntermediateDirectories: true)
        }
        defer { try? files.removeItem(at: root) }

        let launchMarker = root.appendingPathComponent("unexpected-launch")
        let preference = root.appendingPathComponent("target-app.txt")
        let chosenID = "com.brave.Browser"
        try (chosenID + "\n").write(to: preference, atomically: true, encoding: .utf8)

        func makeApp(
            _ name: String, id: String, in directory: URL, executable: Bool = true
        ) throws -> URL {
            let app = directory.appendingPathComponent(name + ".app", isDirectory: true)
            let macos = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let plist = try PropertyListSerialization.data(
                fromPropertyList: [
                    "CFBundleIdentifier": id,
                    "CFBundleExecutable": "Browser",
                    "CFBundlePackageType": "APPL",
                ], format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let binary = macos.appendingPathComponent("Browser")
                try "#!/bin/sh\nprintf launched > \"\(launchMarker.path)\"\n"
                    .write(to: binary, atomically: true, encoding: .utf8)
                try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: binary.path)
            }
            return app
        }

        let brave = try makeApp("Brave", id: chosenID, in: system)
        let alternateBrave = try makeApp("Brave Alternate", id: chosenID, in: custom)
        let chrome = try makeApp("Chrome", id: "com.google.Chrome", in: system)
        let firefox = try makeApp("Firefox", id: "org.mozilla.firefox", in: userApps)
        let brokenBrave = try makeApp("Broken Brave", id: chosenID, in: custom, executable: false)
        let impostor = try makeApp("Brave Impostor", id: "org.example.notBrave", in: system)
        _ = try makeApp("Opener", id: "local.studio.brave-pdf-opener", in: system)
        let stale = custom.appendingPathComponent("Removed Brave.app", isDirectory: true)
        let alias = root.appendingPathComponent("Brave Alias.app", isDirectory: true)
        try files.createSymbolicLink(at: alias, withDestinationURL: alternateBrave)

        func inventory() -> [InstalledBrowser] {
            discoverInstalledBrowsers(
                searchDirectories: [system, userApps],
                additionalApplications: [alternateBrave, alias, brokenBrave],
                registeredApplications: [brave, chrome, firefox, alternateBrave, stale])
        }

        let expected = [
            InstalledBrowser(bundleIdentifier: chosenID, path: brave.path),
            InstalledBrowser(bundleIdentifier: chosenID, path: alternateBrave.path),
            InstalledBrowser(bundleIdentifier: "com.google.Chrome", path: chrome.path),
            InstalledBrowser(bundleIdentifier: "org.mozilla.firefox", path: firefox.path),
        ].sorted { ($0.bundleIdentifier, $0.path) < ($1.bundleIdentifier, $1.path) }
        precondition(inventory() == expected,
                     "Multiple browsers and separate copies must retain their own physical paths")
        precondition(inventory() == expected,
                     "Repeat discovery must not duplicate aliases or change ordering")
        precondition(try JSONDecoder().decode(
            [InstalledBrowser].self, from: JSONEncoder().encode(inventory())) == expected,
            "Multiple installations must survive browser inventory serialization")

        // Exercise the actual PDF-target resolver, not just the read-only
        // inventory: a different installed browser must never replace the
        // selected bundle ID, including when an earlier registration is bad.
        func resolved(_ id: String) -> URL? {
            resolveVerifiedPDFApplication(bundleIdentifier: id, lookupAll: { requested in
                switch requested {
                case chosenID:
                    return [stale, brokenBrave, impostor, brave, alias]
                case "com.google.Chrome":
                    return [brave, chrome]
                case "org.mozilla.firefox":
                    return [firefox]
                default:
                    return []
                }
            })
        }

        precondition(resolved(chosenID) == brave,
                     "Stale, incomplete and mismatched registrations must be skipped")
        precondition(resolved("com.google.Chrome") == chrome,
                     "Chrome must not inherit the chosen Brave installation")
        precondition(resolved("org.mozilla.firefox") == firefox,
                     "Firefox must remain a separately resolvable application")
        precondition(targetSupportsPDF(
            application: resolved(chosenID), registeredPDFHandlers: [brave, chrome]),
            "Only the selected verified Brave installation may receive PDF authorization")
        precondition(!targetSupportsPDF(
            application: resolved(chosenID), registeredPDFHandlers: [alternateBrave, chrome]),
            "A PDF registration for a different Brave copy must not authorize this copy")
        precondition(!targetSupportsPDF(
            application: resolved(chosenID), registeredPDFHandlers: [chrome, firefox]),
            "Other installed PDF browsers cannot authorize the selected Brave target")

        try files.removeItem(at: brave)
        precondition(resolved(chosenID) == alternateBrave,
                     "If the preferred Brave disappears, resolve its next verified installation")
        precondition(targetSupportsPDF(
            application: resolved(chosenID), registeredPDFHandlers: [alternateBrave, chrome]),
            "The surviving selected-browser copy can be verified independently")
        precondition(inventory() == expected.filter { $0.path != brave.path },
                     "Other browsers and the second Brave installation must remain discoverable")

        try files.removeItem(at: alternateBrave)
        precondition(resolved(chosenID) == nil,
                     "Never substitute Chrome or Firefox when all selected copies disappear")
        precondition(!targetSupportsPDF(
            application: resolved(chosenID), registeredPDFHandlers: [chrome, firefox]),
            "An unavailable selected browser must fail the PDF handoff gate")
        precondition(inventory() == expected.filter { $0.path != brave.path &&
                                                     $0.path != alternateBrave.path },
                     "Removing Brave must leave other browsers discoverable")
        precondition(try String(contentsOf: preference, encoding: .utf8) == chosenID + "\n",
                     "Discovery and verification must preserve the user's saved selection")
        precondition(!files.fileExists(atPath: launchMarker.path),
                     "No browser executable may run during inventory or PDF preflight")
        print("PASS: multiple installations, browser-specific PDF resolution and fail-closed selection")
    }
}
