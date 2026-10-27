#!/usr/bin/env python3
"""Exercise native macOS application lookup and stale-bundle rejection."""
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest


class BundleTargetTests(unittest.TestCase):
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
            make_app("WrongIdentity", "com.example.unrelated")
            make_app("MissingExecutable", "com.example.verified", False)
            source = Path(__file__).with_name("launch-scanned-file.swift").read_text()
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
print("Bundle-ID resolution and existence checks passed")
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
