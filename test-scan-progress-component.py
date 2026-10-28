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
panel.show(documentDescription: "one.pdf", stage: .scanning,
           batchProgress: (completed: 0, total: 1))
precondition(panel.progressIndicator.isIndeterminate,
             "A single file has no measured scan percentage")
panel.show(documentDescription: "2 files", stage: .scanning,
           batchProgress: (completed: 0, total: 2))
precondition(!panel.progressIndicator.isIndeterminate)
precondition(panel.progressIndicator.minValue == 0)
precondition(panel.progressIndicator.maxValue == 2)
precondition(panel.progressIndicator.doubleValue == 0)
panel.show(documentDescription: "2 files", stage: .scanning,
           batchProgress: (completed: 1, total: 2))
precondition(panel.progressIndicator.doubleValue == 1)
precondition(panel.progressIndicator.accessibilityLabel()
             == "1 of 2 document requests processed")
panel.show(documentDescription: "invalid", stage: .scanning,
           batchProgress: (completed: 3, total: 2))
precondition(panel.progressIndicator.isIndeterminate,
             "Invalid counts must never imply measured scan progress")
panel.show(documentDescription: "unknown", stage: .scanning)
precondition(panel.progressIndicator.isIndeterminate)
precondition(panel.progressIndicator.accessibilityLabel()
             == "Individual scan progress is unknown")
precondition(panel.protectionProfileLabel.stringValue == "Active protection profile: Built-in")
precondition(panel.protectionProfileDetailsLabel.stringValue == "ClamAV malware scanning · fail-closed")
precondition(panel.protectionProfileLabel.accessibilityLabel() == "Active protection profile: Built-in")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.protectionProfileLabel }) == true)
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.protectionProfileDetailsLabel }) == true)
precondition(panel.protectionProfileLabel.frame.minY > panel.progressIndicator.frame.maxY)
precondition(panel.filenameLabel.frame.minY > panel.protectionProfileLabel.frame.maxY)
precondition(panel.stageLabel.stringValue == ScanProgressStage.queued.label)
precondition(panel.stageLabel.accessibilityLabel() == "Current scanning stage")
precondition(panel.contentView?.subviews.contains(where: { $0 is TwilightReadingView }) == true)
panel.show(documentDescription: "folder/Unicode – report.pdf", stage: .starting)
precondition(panel.filenameLabel.stringValue == "folder/Unicode – report.pdf")
precondition(panel.stageLabel.stringValue == "Starting safety checks…")
panel.show(documentDescription: "3 documents", stage: .scanning)
precondition(panel.filenameLabel.stringValue == "3 documents")
precondition(panel.protectionProfileLabel.stringValue == "Active protection profile: Built-in")
precondition(panel.protectionProfileDetailsLabel.stringValue == "ClamAV malware scanning · fail-closed")
precondition(panel.stageLabel.stringValue == "Scanning and verifying document…")
precondition(panel.contentView?.subviews.contains(where: { $0 === panel.cancelButton }) == true)
panel.cancelButton.performClick(nil)
precondition(owner.pressed, "The caller owns cancellation")
panel.orderOut(nil)
print("PASS: one shared native progress panel, stage transitions, animation and caller-owned Cancel")
""")
            binary = root / "progress"
            subprocess.run(["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                            str(harness), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()
