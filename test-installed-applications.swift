import Foundation

@main
struct InstalledApplicationTests {
    static func main() throws {
        let manager = FileManager.default
        let root = manager.temporaryDirectory.appendingPathComponent(
            "pdf-magic-installed-apps-" + UUID().uuidString, isDirectory: true)
        try manager.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? manager.removeItem(at: root) }

        func makeApp(
            _ folder: String,
            identifier: String,
            displayName: String,
            executable: Bool = true
        ) throws -> URL {
            let app = root.appendingPathComponent(folder + ".app", isDirectory: true)
            let binaries = app.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try manager.createDirectory(at: binaries, withIntermediateDirectories: true)
            let details: [String: Any] = [
                "CFBundleIdentifier": identifier,
                "CFBundleDisplayName": displayName,
                "CFBundleExecutable": "TestApp",
                "CFBundlePackageType": "APPL",
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: details, format: .xml, options: 0)
            try plist.write(to: app.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let program = binaries.appendingPathComponent("TestApp")
                try "#!/bin/sh\nexit 0\n".write(to: program, atomically: true, encoding: .utf8)
                try manager.setAttributes([.posixPermissions: 0o755],
                                          ofItemAtPath: program.path)
            }
            return app
        }

        let alpha = try makeApp("Viewer Alpha", identifier: "org.example.alpha",
                                displayName: "Alpha Reader")
        let beta = try makeApp("Viewer Beta", identifier: "org.example.beta",
                               displayName: "Beta Reader")
        let stale = root.appendingPathComponent("Missing.app")
        let broken = try makeApp("Unusable", identifier: "org.example.unusable",
                                 displayName: "Broken Reader", executable: false)
        let noIdentifier = try makeApp("Wrong", identifier: "org.example.wrong",
                                       displayName: "Wrong Reader")
        // Invalid bundle identifiers are not available as valid app metadata.
        let invalidInfo = noIdentifier.appendingPathComponent("Contents/Info.plist")
        let invalidPlist = try PropertyListSerialization.data(
            fromPropertyList: ["CFBundleDisplayName": "Wrong Reader",
                               "CFBundleExecutable": "TestApp",
                               "CFBundlePackageType": "APPL"],
            format: .xml, options: 0)
        try invalidPlist.write(to: invalidInfo)
        let pdf = root.appendingPathComponent("Reader.pdf")
        try "%PDF-1.4\n".write(to: pdf, atomically: true, encoding: .utf8)
        let paths = [beta.path, stale.path, broken.path, alpha.path, alpha.path,
                     noIdentifier.path, pdf.path, "Viewer Alpha.app"]

        let results = matchingInstalledApplications(query: " reader ", paths: paths)
        precondition(results.map(\.name) == ["Alpha Reader", "Beta Reader"],
                     "Should match case-insensitively, deduplicate and sort")
        precondition(results[0].bundleIdentifier == "org.example.alpha")
        precondition(results[0].path == alpha.path)
        precondition(matchingInstalledApplications(query: "ORG.EXAMPLE.BETA", paths: paths)
                     .map(\.path) == [beta.path], "Must match bundle identifiers")
        precondition(matchingInstalledApplications(query: "Viewer Alpha", paths: paths)
                     .map(\.path) == [alpha.path], "Must match app bundle names")
        precondition(matchingInstalledApplications(query: "not installed", paths: paths).isEmpty)
        precondition(matchingInstalledApplications(query: "  ", paths: paths).isEmpty)
        precondition(matchingInstalledApplications(query: String(repeating: "x", count: 257),
                                                  paths: paths).isEmpty)

        let newlinePath = "/Applications/Line\nBreak.app"
        let bytes = Data(("/Applications/Alpha.app\0" + newlinePath + "\0").utf8)
        precondition(decodeSpotlightPaths(bytes) == ["/Applications/Alpha.app", newlinePath],
                     "NUL-separated Spotlight results must preserve arbitrary filenames")
        print("PASS: installed-app discovery matches validated bundles without opening them.")
    }
}
