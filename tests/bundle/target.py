#!/usr/bin/env python3
"""Exercise native macOS application lookup and stale-bundle rejection."""
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest


class BundleTargetTests(unittest.TestCase):
    def test_closed_browser_launches_and_receives_selected_pdf(self):
        if sys.platform != "darwin":
            self.skipTest("NSWorkspace requires macOS")
        # The existing macOS CI bundle-test step runs this integration test,
        # avoiding a second shared workflow edit during concurrent PR merges.
        cold_start = (Path(__file__).resolve().parents[2] / "tests/browser/cold-start.py")
        result = subprocess.run(
            [sys.executable, str(cold_start), "-v"],
            capture_output=True, text=True, timeout=150,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_registered_application_must_exist_and_match_bundle_identifier(self):
        if sys.platform != "darwin":
            self.skipTest("NSWorkspace requires macOS")
        with tempfile.TemporaryDirectory(prefix="opener-bundle-target-") as directory:
            root = Path(directory)

            def make_app(name, identifier, executable=True):
                app = root / (name + ".app")
                macos = app / "Contents" / "MacOS"
                macos.mkdir(parents=True)
                info = {
                    "CFBundleIdentifier": identifier,
                    "CFBundleExecutable": "Example",
                    "CFBundlePackageType": "APPL",
                }
                with (app / "Contents" / "Info.plist").open("wb") as output:
                    plistlib.dump(info, output)
                if executable:
                    program = macos / "Example"
                    program.write_text("#!/bin/sh\nexit 0\n")
                    program.chmod(0o755)
                return app

            make_app("Installed", "com.example.verified")
            make_app("SecondCopy", "com.example.verified")
            make_app("WrongIdentity", "com.example.unrelated")
            make_app("MicrosoftEdge", "com.microsoft.edgemac")
            make_app("EdgeImpostor", "com.example.not-edge")
            make_app("EdgeMissingExecutable", "com.microsoft.edgemac", False)
            make_app("MissingExecutable", "com.example.verified", False)
            make_app("PDFOpener", "local.studio.brave-pdf-opener")
            pdf = root / "local document.PDF"
            pdf.write_bytes(b"%PDF-1.4\\n")
            source = (Path(__file__).resolve().parents[2] / "launch-scanned-file.swift").read_text()
            prelude, marker, _ = source.partition(
                "guard launch(Array(CommandLine.arguments.dropFirst())) else {"
            )
            self.assertTrue(marker, "Native launcher entry point not found")
            harness = prelude + """
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let wanted = "com.example.verified"
func fakeLookup(_ app: String) -> (String) -> URL? {
    return { _ in root.appendingPathComponent(app + ".app", isDirectory: true) }
}
precondition(resolveTargetApplication(bundleIdentifier: wanted,
                                      lookup: fakeLookup("Installed")) != nil)
// Launch Services ranks duplicate installations. Select the first *valid*
// registered copy; skip stale, spoofed, and nonexecutable registrations.
func allCandidates(_ names: [String]) -> (String) -> [URL] {
    return { _ in names.map { root.appendingPathComponent($0 + ".app", isDirectory: true) } }
}
let first = resolveTargetApplication(bundleIdentifier: wanted,
    lookupAll: allCandidates(["NotInstalled", "WrongIdentity",
                              "MissingExecutable", "Installed", "SecondCopy"]))
precondition(first == root.appendingPathComponent("Installed.app"))
let second = resolveTargetApplication(bundleIdentifier: wanted,
    lookupAll: allCandidates(["SecondCopy", "Installed"]))
precondition(second == root.appendingPathComponent("SecondCopy.app"))
precondition(resolveTargetApplication(bundleIdentifier: wanted,
    lookupAll: allCandidates(["WrongIdentity", "MissingExecutable", "NotInstalled"])) == nil)
precondition(resolveTargetApplication(bundleIdentifier: wanted,
    lookupAll: { _ in [] }) == nil)
precondition(resolveTargetApplication(bundleIdentifier: "local.studio.brave-pdf-opener",
    lookupAll: allCandidates(["PDFOpener", "Installed"])) == nil)
precondition(resolveTargetApplication(bundleIdentifier: "com.microsoft.edgemac",
                                      lookup: fakeLookup("MicrosoftEdge")) != nil)
precondition(resolveTargetApplication(bundleIdentifier: "com.microsoft.edgemac",
                                      lookup: fakeLookup("EdgeImpostor")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: "com.microsoft.edgemac",
                                      lookup: fakeLookup("EdgeMissingExecutable")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: "com.microsoft.edgemac",
                                      lookup: fakeLookup("NotInstalled")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: wanted,
                                      lookup: fakeLookup("WrongIdentity")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: wanted,
                                      lookup: fakeLookup("MissingExecutable")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: wanted,
                                      lookup: fakeLookup("NotInstalled")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: wanted,
                                      lookup: { _ in nil }) == nil)
precondition(resolveTargetApplication(bundleIdentifier: "",
                                      lookup: fakeLookup("Installed")) == nil)
// The scan gate may register itself as a PDF handler; never hand it the
// approved PDF again, even when asked to do so by bundle identifier.
precondition(resolveTargetApplication(bundleIdentifier: "local.studio.brave-pdf-opener",
                                      lookup: fakeLookup("PDFOpener")) == nil)
// Direct launcher invocations must not fall back to the system PDF handler,
// which macOS may have set to PDF Magic Opener itself.
let pdf = root.appendingPathComponent("local document.PDF")
precondition(launch([pdf.path]) == false)
print("Bundle-ID resolution and non-recursive PDF launch checks passed")
"""
            file = root / "test.swift"
            file.write_text(harness)
            binary = root / "bundle-target-test"
            subprocess.run(
                ["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                 str(file), "-o", str(binary)], check=True,
            )
            run = subprocess.run([str(binary), str(root)], check=True,
                                 capture_output=True, text=True, timeout=20)
            self.assertIn("checks passed", run.stdout)


if __name__ == "__main__":
    unittest.main()
