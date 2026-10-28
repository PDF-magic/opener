#!/usr/bin/env python3
"""Test path-free scanner initialization diagnostics in the native progress owner."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
OPENER = ROOT / "brave-pdf-opener.swift"
PROGRESS = ROOT / "scan-progress-view.swift"
PREFERENCE = ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift"


class ScannerInitializationErrorTests(unittest.TestCase):
    def test_startup_failure_is_wired_to_visible_warning_without_bypassing_scan(self):
        source = OPENER.read_text(encoding="utf-8")
        self.assertIn("return ScannerInitializationError.missingHelper", source)
        self.assertIn("return ScannerInitializationError.launchFailed", source)
        self.assertIn("let alert = scanFailureAlert(for: failure)", source)
        self.assertIn("alert.runModal()", source)
        self.assertIn("if process.terminationStatus != 0 {", source)
        self.assertIn("if cancelled { return nil }", source)
        self.assertIn("process.executableURL = URL(fileURLWithPath: \"/bin/bash\")", source)
        self.assertIn("self.activeProcesses[path] = process", source)
        self.assertIn("self.startQueuedScans()", source)
        self.assertIn("self.panel?.orderOut(nil)", source)

    def test_native_alert_classifies_only_known_initialization_failures(self):
        source = OPENER.read_text(encoding="utf-8").split(
            "@main\nstruct PDFMagicOpenerEntry {", 1)[0]
        self.assertIn("enum ScannerInitializationError", source)
        with tempfile.TemporaryDirectory(prefix="opener-scanner-startup-") as directory:
            root = Path(directory)
            harness = root / "test.swift"
            harness.write_text(
                source
                + "\n" + PROGRESS.read_text(encoding="utf-8")
                + "\n" + PREFERENCE.read_text(encoding="utf-8").replace(
                    "import Foundation\n", "")
                + r"""
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let startupMessages = [
    ScannerInitializationError.missingHelper,
    ScannerInitializationError.launchFailed,
    "ClamAV is unavailable. Run the Allow and Open installer again.",
    "Malware signatures are unavailable. Run update-malware-signatures.sh.",
    "Malware signatures have not been checked in 48 hours. Run update-malware-signatures.sh.",
    "The malware signature database is incomplete. Run update-malware-signatures.sh."
]
for detail in startupMessages {
    let warning = scanFailureAlert(for: detail + "\n")
    precondition(warning.alertStyle == .warning)
    precondition(warning.messageText == "Scanner initialization failed")
    precondition(warning.informativeText.contains(detail))
    precondition(warning.informativeText.contains("The document was not opened."))
    precondition(warning.buttons.first?.title == "OK")
}
let normal = scanFailureAlert(for: "Malware or an unscannable item was detected; opening was stopped.")
precondition(normal.messageText == "Opening stopped", "Other blocked verdicts retain their warning")
precondition(normal.informativeText.contains("Malware or an unscannable item"))
let injected = scanFailureAlert(for: startupMessages[2] + "\n/private/secret.pdf")
precondition(injected.messageText == "Opening stopped",
             "Unknown stderr must not masquerade as a known initialization failure")
let cancelled = scanFailureAlert(for: "The scan was cancelled; opening was stopped.")
precondition(cancelled.messageText == "Opening stopped",
             "Cancellation is not a scanner initialization error")
print("PASS: known scanner initialization failures get actionable native warnings")
""",
                encoding="utf-8"
            )
            binary = root / "startup-alert"
            subprocess.run(["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                            str(harness), "-o", str(binary)], check=True, timeout=90)
            subprocess.run([str(binary)], check=True, timeout=20)


if __name__ == "__main__":
    unittest.main()
