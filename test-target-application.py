#!/usr/bin/env python3
"""Verify bundle-ID resolution and existing-application checks."""
import json
import plistlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from target_application import PDF_DEFAULT_BUNDLE_ID, resolve_target_application


class TargetApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.application = Path(self.temp.name) / "Browser Example.app"
        self.application.mkdir()

    def test_trusted_helper_returns_installed_application(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps(
            {"path": str(self.application)}), "")
        with patch("target_application.subprocess.run", return_value=completed) as run:
            found = resolve_target_application(PDF_DEFAULT_BUNDLE_ID, resolver="/resolver")
        self.assertEqual(found, str(self.application))
        run.assert_called_once_with(
            ["/resolver", PDF_DEFAULT_BUNDLE_ID], capture_output=True,
            text=True, check=True, timeout=10,
        )

    def test_missing_or_invalid_apps_fail_closed(self):
        cases = [
            subprocess.CalledProcessError(1, "/resolver"),
            subprocess.TimeoutExpired("/resolver", 10),
        ]
        for error in cases:
            with self.subTest(error=type(error).__name__):
                with patch("target_application.subprocess.run", side_effect=error):
                    with self.assertRaisesRegex(RuntimeError, "unavailable"):
                        resolve_target_application(PDF_DEFAULT_BUNDLE_ID, resolver="/resolver")
        for output in (
            "not json", "{}", json.dumps({"path": "/no/such/application.app"}),
            json.dumps({"path": str(self.application / "file")}),
            json.dumps({"path": ""}), json.dumps({"path": 3}),
        ):
            with self.subTest(output=output):
                with patch("target_application.subprocess.run",
                           return_value=subprocess.CompletedProcess([], 0, output, "")):
                    with self.assertRaisesRegex(RuntimeError, "unavailable"):
                        resolve_target_application(PDF_DEFAULT_BUNDLE_ID, resolver="/resolver")

    def test_rejects_missing_bundle_identifier(self):
        with patch("target_application.subprocess.run") as run:
            with self.assertRaisesRegex(RuntimeError, "unavailable"):
                resolve_target_application("", resolver="/resolver")
        run.assert_not_called()

    @unittest.skipUnless(sys.platform == "darwin", "native NSWorkspace tests require macOS")
    def test_native_resolver_verifies_registered_app_bundle(self):
        root = Path(self.temp.name)
        def bundle(name, bundle_id, executable=True):
            app = root / (name + ".app")
            contents = app / "Contents"
            macos = contents / "MacOS"
            macos.mkdir(parents=True)
            with (contents / "Info.plist").open("wb") as stream:
                plistlib.dump({
                    "CFBundleIdentifier": bundle_id,
                    "CFBundleExecutable": "Example",
                    "CFBundlePackageType": "APPL",
                }, stream)
            if executable:
                path = macos / "Example"
                path.write_text("#!/bin/sh\nexit 0\n")
                path.chmod(0o755)
            return app
        bundle("Valid", "com.example.test")
        bundle("WrongIdentity", "com.example.other")
        bundle("NoExecutable", "com.example.test", executable=False)
        source = Path(__file__).with_name("target-app-resolver.swift").read_text()
        functions = source.split("let arguments = CommandLine.arguments\n", 1)
        self.assertEqual(len(functions), 2)
        harness = functions[0] + """
let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let targetID = "com.example.test"
func lookup(_ name: String) -> (String) -> URL? {
    return { _ in root.appendingPathComponent(name + ".app", isDirectory: true) }
}
precondition(resolveTargetApplication(bundleIdentifier: targetID, lookup: lookup("Valid")) != nil)
precondition(resolveTargetApplication(bundleIdentifier: targetID, lookup: lookup("WrongIdentity")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: targetID, lookup: lookup("NoExecutable")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: targetID, lookup: lookup("Missing")) == nil)
precondition(resolveTargetApplication(bundleIdentifier: targetID, lookup: { _ in nil }) == nil)
precondition(resolveTargetApplication(bundleIdentifier: "", lookup: lookup("Valid")) == nil)
print("Native bundle ID and executable validation passed")
"""
        swift = root / "test-target.swift"
        swift.write_text(harness)
        binary = root / "test-target"
        subprocess.run(["/usr/bin/xcrun", "swiftc", str(swift), "-o", str(binary)], check=True)
        result = subprocess.run([str(binary), str(root)], check=True,
                                capture_output=True, text=True, timeout=15)
        self.assertIn("validation passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
