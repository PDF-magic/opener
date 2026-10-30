#!/usr/bin/env python3
"""Exercise the real macOS PDF handoff when its target application is already running.

The test browser is an isolated, harmless macOS .app fixture. No installed
browser or user file associations are touched; the Swift launcher still uses
NSWorkspace.open(_:withApplicationAt:configuration:completionHandler:).
"""
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent
BUNDLE_ID = "org.pdfmagic.tests.running-browser"


class AlreadyRunningBrowserTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "darwin", "NSWorkspace requires macOS")
    def test_pdf_is_delivered_to_existing_browser_without_starting_another(self):
        with tempfile.TemporaryDirectory(prefix="pdf-running-browser-") as directory:
            root = Path(directory)
            browser = root / "RunningBrowser.app"
            macos = browser / "Contents" / "MacOS"
            macos.mkdir(parents=True)
            executable = macos / "RunningBrowser"
            with (browser / "Contents" / "Info.plist").open("wb") as out:
                plistlib.dump({
                    "CFBundleIdentifier": BUNDLE_ID,
                    "CFBundleExecutable": "RunningBrowser",
                    "CFBundleName": "RunningBrowser",
                    "CFBundlePackageType": "APPL",
                    "LSUIElement": True,
                    "CFBundleDocumentTypes": [{
                        "CFBundleTypeName": "PDF document",
                        "CFBundleTypeRole": "Viewer",
                        "LSItemContentTypes": ["com.adobe.pdf"],
                    }],
                }, out)
            fake_browser_source = root / "fake-browser.swift"
            fake_browser_source.write_text(r"""
import AppKit
import Foundation

final class BrowserDelegate: NSObject, NSApplicationDelegate {
    private var bundle: URL { Bundle.main.bundleURL }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let pid = String(ProcessInfo.processInfo.processIdentifier)
        try? pid.write(to: bundle.appendingPathComponent("running.pid"),
                       atomically: true, encoding: .utf8)
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        let data = (urls.map { $0.path }.joined(separator: "\n") + "\n")
            .data(using: .utf8)!
        let output = bundle.appendingPathComponent("opened-paths.txt")
        if FileManager.default.fileExists(atPath: output.path),
           let handle = try? FileHandle(forWritingTo: output) {
            defer { try? handle.close() }
            _ = try? handle.seekToEnd()
            try? handle.write(contentsOf: data)
        } else {
            try? data.write(to: output)
        }
    }
}

let app = NSApplication.shared
let delegate = BrowserDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
""")
            subprocess.run(
                ["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                 str(fake_browser_source), "-o", str(executable)],
                check=True, timeout=90,
            )
            executable.chmod(0o755)

            source = (ROOT / "launch-scanned-file.swift").read_text()
            prelude, marker, _ = source.partition(
                "guard launch(Array(CommandLine.arguments.dropFirst())) else {"
            )
            self.assertTrue(marker, "Native launcher entry point not found")
            harness = root / "launch-test.swift"
            harness.write_text(prelude + r"""
let appURL = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
let pdfURL = URL(fileURLWithPath: CommandLine.arguments[2])
let selected = "org.pdfmagic.tests.running-browser"
let lookedUp: (String) -> URL? = { identifier in
    identifier == selected ? appURL : nil
}
precondition(launch(["--bundle-id", selected, pdfURL.path],
                    applicationLookup: lookedUp),
             "An approved PDF should reach the already-running browser")
""")
            native_test = root / "launch-test"
            subprocess.run(
                ["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                 str(harness), "-o", str(native_test)],
                check=True, timeout=90,
            )

            pdf = root / "a scanned document – ready.PDF"
            pdf.write_bytes(b"%PDF-1.4\n% harmless test fixture\n")
            running = browser / "running.pid"
            opened = browser / "opened-paths.txt"
            original_pid = None
            try:
                # Launch the app through Launch Services before handing off
                # the PDF, rather than merely simulating a 'running' flag.
                subprocess.run(["/usr/bin/open", "-a", str(browser)],
                               check=True, timeout=15)
                self.assertTrue(self.wait_for(running.exists, 15),
                                "The browser fixture did not start")
                original_pid = int(running.read_text())
                os.kill(original_pid, 0)
                subprocess.run([str(native_test), str(browser), str(pdf)],
                               check=True, timeout=45)
                self.assertTrue(self.wait_for(opened.exists, 15),
                                "The already-running app did not receive the PDF")
                delivered = opened.read_text().splitlines()
                self.assertEqual(len(delivered), 1,
                                 "The running browser must receive exactly one PDF")
                # macOS resolves /var to /private/var when passing a file URL
                # through Launch Services. Compare file identities, not aliases.
                self.assertEqual(Path(delivered[0]).resolve(), pdf.resolve(),
                                 "The existing browser must receive the selected PDF")
                self.assertEqual(int(running.read_text()), original_pid,
                                 "The launch must reuse the original browser process")
                os.kill(original_pid, 0)
            finally:
                if original_pid is not None:
                    try:
                        os.kill(original_pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass

    @staticmethod
    def wait_for(predicate, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return True
            time.sleep(0.1)
        return predicate()


if __name__ == "__main__":
    unittest.main()
