#!/usr/bin/env python3
"""Compile the reusable native progress UI and verify opener-independent rendering."""
from pathlib import Path
import subprocess
import tempfile
import unittest

COMPONENT = Path(__file__).with_name("scan-progress-view.swift")


class ScanProgressComponentTests(unittest.TestCase):
    def test_existing_native_progress_panel_can_be_used_without_pdf_opener(self):
        source = COMPONENT.read_text()
        self.assertIn("final class ScanProgressPanel: NSPanel", source)
        self.assertNotIn("scan-and-open.py", source)
        self.assertNotIn("Process()", source)
        with tempfile.TemporaryDirectory(prefix="opener-scan-progress-") as directory:
            root = Path(directory)
            (root / "twilight-reading.png").write_bytes(
                Path(__file__).with_name("twilight-reading.png").read_bytes())
            harness = root / "test.swift"
            harness.write_text(source + """
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
final class CancelOwner: NSObject {
    var pressed = false
    @objc func cancel(_ sender: NSButton) { pressed = true }
}
let owner = CancelOwner()
let panel = ScanProgressPanel(cancelTarget: owner, cancelAction: #selector(CancelOwner.cancel(_:)))
precondition(panel.title == "PDF Magic Opener — Scanning")
precondition(!panel.hidesOnDeactivate && panel.level == .floating)
precondition(panel.progressIndicator.isIndeterminate)
precondition(panel.cancelButton.title == "Cancel")
precondition(panel.contentView?.subviews.contains(where: { $0 is TwilightReadingView }) == true)
panel.show(documentDescription: "folder/Unicode – report.pdf")
precondition(panel.filenameLabel.stringValue == "folder/Unicode – report.pdf")
panel.show(documentDescription: "3 documents")
precondition(panel.filenameLabel.stringValue == "3 documents")
precondition(panel.destinationBrowserLabel.stringValue == "Destination browser: Unavailable")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.destinationBrowserLabel }) == true)
precondition(panel.destinationBrowserLabel.frame.minY > panel.progressIndicator.frame.maxY)
precondition(panel.filenameLabel.frame.minY > panel.destinationBrowserLabel.frame.maxY)

let fixture = FileManager.default.temporaryDirectory
    .appendingPathComponent("selected-browser-\(UUID().uuidString)", isDirectory: true)
try FileManager.default.createDirectory(at: fixture, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: fixture) }
let preference = fixture.appendingPathComponent("target-app.txt")
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Brave",
             "missing preferences must use the established Brave default")
try "com.google.Chrome\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Google Chrome")
panel.updateDestinationBrowser(SelectedDestinationBrowser.displayName(in: fixture))
precondition(panel.destinationBrowserLabel.stringValue == "Destination browser: Google Chrome")
precondition(panel.destinationBrowserLabel.accessibilityLabel() == "Destination browser: Google Chrome")
try "system-default-browser\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "System default browser")
try "org.mozilla.firefox\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Firefox")
try "com.example.viewer\n".write(to: preference, atomically: true, encoding: .ascii)
precondition(SelectedDestinationBrowser.displayName(in: fixture) ==
             "Custom application (com.example.viewer)", "custom selection must not be overwritten")
for invalid in ["local.studio.brave-pdf-opener", "bad..identifier", "invalid path", ""] {
    try invalid.write(to: preference, atomically: true, encoding: .ascii)
    precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Unavailable",
                 "invalid identifiers must never appear as selected browsers")
}
try FileManager.default.removeItem(at: preference)
let elsewhere = fixture.appendingPathComponent("elsewhere")
try "com.apple.Safari\n".write(to: elsewhere, atomically: true, encoding: .ascii)
try FileManager.default.createSymbolicLink(at: preference, withDestinationURL: elsewhere)
precondition(SelectedDestinationBrowser.displayName(in: fixture) == "Unavailable",
             "never follow a symlinked preference file")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.cancelButton }) == true)
panel.cancelButton.performClick(nil)
precondition(owner.pressed, "The caller owns cancellation")
panel.orderOut(nil)
print("PASS: one shared native progress panel, animation, updates and caller-owned Cancel")
""")
            binary = root / "progress"
            subprocess.run(["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                            str(harness), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
