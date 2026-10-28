import Foundation

@main
struct CustomPDFApplicationSelectionTests {
    static func main() throws {
        let files = FileManager.default
        let root = files.temporaryDirectory
            .appendingPathComponent("opener-manual-selection-" + UUID().uuidString, isDirectory: true)
        try files.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? files.removeItem(at: root) }

        func app(_ directory: String, _ name: String, _ id: String, executable: Bool = true) throws -> URL {
            let path = root.appendingPathComponent(directory, isDirectory: true)
                .appendingPathComponent(name + ".app", isDirectory: true)
            let macos = path.appendingPathComponent("Contents/MacOS", isDirectory: true)
            try files.createDirectory(at: macos, withIntermediateDirectories: true)
            let metadata: [String: String] = [
                "CFBundleIdentifier": id,
                "CFBundleExecutable": "Executable",
                "CFBundlePackageType": "APPL",
            ]
            let plist = try PropertyListSerialization.data(
                fromPropertyList: metadata, format: .xml, options: 0)
            try plist.write(to: path.appendingPathComponent("Contents/Info.plist"))
            if executable {
                let program = macos.appendingPathComponent("Executable")
                try "#!/bin/sh\nexit 0\n".write(to: program, atomically: true, encoding: .utf8)
                try files.setAttributes([.posixPermissions: 0o755], ofItemAtPath: program.path)
            }
            return path
        }

        let good = try app("Main", "My Browser", "org.example.customBrowser")
        let duplicate = try app("Other", "My Browser", "org.example.customBrowser")
        let noExecutable = try app("Bad", "Incomplete", "org.example.incomplete", executable: false)
        let scanGate = try app("Bad", "Scan Gate", "local.studio.brave-pdf-opener")
        let invalid = try app("Bad", "Invalid", "org..invalid")
        let document = root.appendingPathComponent("not-an-application.txt")
        try "test".write(to: document, atomically: true, encoding: .utf8)
        let useGood: (String) -> URL? = { id in id == "org.example.customBrowser" ? good : nil }
        let accepts: (String) -> Bool = { _ in true }

        precondition(eligibleCustomBundleIdentifier(
            at: good, resolve: useGood, supportsPDF: accepts
        ) == "org.example.customBrowser", "Explicit registered and PDF-capable .app must be accepted")
        precondition(eligibleCustomBundleIdentifier(
            at: duplicate, resolve: useGood, supportsPDF: accepts
        ) == nil, "Another installation with the same bundle ID must not silently replace the selection")
        precondition(eligibleCustomBundleIdentifier(
            at: good, resolve: { _ in nil }, supportsPDF: accepts
        ) == nil, "Unregistered apps cannot be selected by bundle ID")
        precondition(eligibleCustomBundleIdentifier(
            at: good, resolve: useGood, supportsPDF: { _ in false }
        ) == nil, "Apps without verified PDF capability must be rejected")
        precondition(eligibleCustomBundleIdentifier(
            at: noExecutable, resolve: { _ in noExecutable }, supportsPDF: accepts
        ) == nil, "Missing executables must be rejected")
        precondition(eligibleCustomBundleIdentifier(
            at: scanGate, resolve: { _ in scanGate }, supportsPDF: accepts
        ) == nil, "The opener cannot select itself as the post-scan app")
        precondition(eligibleCustomBundleIdentifier(
            at: invalid, resolve: { _ in invalid }, supportsPDF: accepts
        ) == nil, "Malformed bundle identifiers must fail closed")
        precondition(eligibleCustomBundleIdentifier(
            at: document, resolve: useGood, supportsPDF: accepts
        ) == nil, "Regular documents cannot be chosen as applications")
        precondition(eligibleCustomBundleIdentifier(
            at: root.appendingPathComponent("Missing.app"),
            resolve: useGood, supportsPDF: accepts
        ) == nil, "Missing app bundles must be rejected")

        let alias = root.appendingPathComponent("Selected Alias.app")
        try files.createSymbolicLink(at: alias, withDestinationURL: good)
        precondition(eligibleCustomBundleIdentifier(
            at: alias, resolve: useGood, supportsPDF: accepts
        ) == "org.example.customBrowser", "A working app symlink may resolve to the registered application")
        print("PASS: manual application selection preserves exact verified PDF destination")
    }
}
