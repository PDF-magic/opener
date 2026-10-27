#!/usr/bin/env python3
"""Verify the native PDF launcher starts an installed app that is not running.

A signed, temporary AppKit viewer stands in for a closed browser. The real
NSWorkspace PDF open path must launch it and deliver the exact local PDF.
No installed browser, default association, ClamAV policy, or user setting
is modified.
"""
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
import uuid


APP_SOURCE = r"""
import AppKit

final class ReceiptDelegate: NSObject, NSApplicationDelegate {
    private func record(_ paths: [String]) {
        guard !paths.isEmpty,
              let receipt = Bundle.main.object(forInfoDictionaryKey: "TestPDFReceipt") as? String else {
            return
        }
        try? paths.joined(separator: "\n").write(
            toFile: receipt, atomically: true, encoding: .utf8
        )
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        record(urls.map { $0.path })
    }

    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        record(filenames)
        sender.reply(toOpenOrPrint: .success)
    }

    func application(_ sender: NSApplication, openFile filename: String) -> Bool {
        record([filename])
        return true
    }
}

let app = NSApplication.shared
let delegate = ReceiptDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
DispatchQueue.main.asyncAfter(deadline: .now() + 25) {
    NSApp.terminate(nil)
}
app.run()
"""

HARNESS_SOURCE = r"""
let bundle = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let pdf = CommandLine.arguments[2]
let marker = CommandLine.arguments[3]
let identifier = CommandLine.arguments[4]

precondition(
    NSRunningApplication.runningApplications(withBundleIdentifier: identifier).isEmpty,
    "The browser fixture must start closed"
)
let launched = launch(
    ["--bundle-id", identifier, pdf],
    applicationLookup: { selected in selected == identifier ? bundle : nil }
)
precondition(launched, "The native launcher must start the stopped application")

let deadline = Date().addingTimeInterval(20)
var received: String?
while Date() < deadline {
    received = try? String(contentsOfFile: marker, encoding: .utf8)
    if received == pdf { break }
    Thread.sleep(forTimeInterval: 0.1)
}
precondition(received == pdf, "The newly launched app must receive the selected PDF (actual: \(received ?? "none"))")
let running = NSRunningApplication.runningApplications(withBundleIdentifier: identifier)
precondition(!running.isEmpty, "The target application must be running after cold launch")
for application in running { _ = application.terminate() }
print("PASS: a stopped, verified app launched and received the original PDF")
"""


class BrowserColdStartTests(unittest.TestCase):
    def test_stopped_browser_bundle_opens_approved_pdf(self):
        if sys.platform != "darwin":
            self.skipTest("NSWorkspace browser cold start requires macOS")

        source = Path(__file__).with_name("launch-scanned-file.swift").read_text()
        before, marker, _ = source.partition(
            "guard launch(Array(CommandLine.arguments.dropFirst())) else {"
        )
        self.assertTrue(marker, "Native launch helper entry point not found")
        with tempfile.TemporaryDirectory(prefix="pdf-magic-cold-browser-") as folder:
            root = Path(folder)
            identifier = "local.pdfmagic.coldbrowser." + uuid.uuid4().hex
            receipt = root / "opened-pdf.txt"
            pdf = root / "Selected report – 2026.PDF"
            pdf.write_bytes(b"%PDF-1.4\nLocal test PDF\n")

            bundle = root / "ClosedBrowser.app"
            executable = bundle / "Contents" / "MacOS" / "ClosedBrowser"
            executable.parent.mkdir(parents=True)
            info = {
                "CFBundleIdentifier": identifier,
                "CFBundleExecutable": "ClosedBrowser",
                "CFBundleName": "ClosedBrowser",
                "CFBundlePackageType": "APPL",
                "LSUIElement": True,
                "TestPDFReceipt": str(receipt),
                "CFBundleDocumentTypes": [{
                    "CFBundleTypeName": "PDF Document",
                    "CFBundleTypeRole": "Viewer",
                    "LSItemContentTypes": ["com.adobe.pdf"],
                }],
            }
            with (bundle / "Contents" / "Info.plist").open("wb") as target:
                plistlib.dump(info, target)

            app_source = root / "closed-browser.swift"
            app_source.write_text(APP_SOURCE)
            subprocess.run(
                ["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                 str(app_source), "-o", str(executable)],
                check=True, timeout=60,
            )
            subprocess.run(
                ["/usr/bin/codesign", "--force", "--sign", "-", str(bundle)],
                check=True, timeout=20, capture_output=True, text=True,
            )

            harness = root / "test-cold-start.swift"
            harness.write_text(before + HARNESS_SOURCE)
            binary = root / "cold-start-test"
            subprocess.run(
                ["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                 str(harness), "-o", str(binary)],
                check=True, timeout=60,
            )
            result = subprocess.run(
                [str(binary), str(bundle), str(pdf), str(receipt), identifier],
                capture_output=True, text=True, timeout=65,
            )
            self.assertEqual(
                result.returncode, 0,
                "macOS cold-start harness failed:\n" + result.stdout + result.stderr,
            )
            self.assertIn("PASS: a stopped, verified app launched", result.stdout)
            self.assertEqual(receipt.read_text(), str(pdf))


if __name__ == "__main__":
    unittest.main()
