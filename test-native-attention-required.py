#!/usr/bin/env python3
"""Verify that the native scan owner retains a failed scan until user dismissal."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent


class AttentionRequiredTests(unittest.TestCase):
    def test_failed_scan_requires_explicit_close_without_bypassing_scan(self):
        source = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
        progress = (ROOT / "scan-progress-view.swift").read_text(encoding="utf-8")
        preference = (ROOT / "PDFMagicOpenerApp/ScanProgressPreference.swift").read_text()
        self.assertEqual(source.count("alert.runModal()"), 1)
        self.assertIn("if pending.isEmpty && attentionRequired {", source)
        self.assertIn("panel?.showAttentionRequired(documentDescription:", source)
        self.assertIn("!self.attentionRequired", source)
        self.assertNotIn("ScanProgressPreference", source.split("private func startQueuedScans()")[1])
        self.assertIn("process.arguments = [script.path, path]", source)
        self.assertNotIn("Process()", progress)
        native = source.split("@main\nstruct PDFMagicOpenerEntry {", 1)[0]
        native = native.replace(
            "alert.runModal()",
            """
            precondition(alert.buttons.first?.title == "OK",
                         "The native failure alert must still require acknowledgement")
            let panels = NSApp.windows.compactMap { $0 as? ScanProgressPanel }
            precondition(panels.count == 1 && panels[0].isVisible,
                         "Failure warning must keep the progress window open")
            precondition(panels[0].cancelButton.title == "Close",
                         "Blocked scan must require explicit dismissal")
            print("PASS: failure warning retains the progress window")
            """, 1,
        )
        with tempfile.TemporaryDirectory(prefix="opener-attention-") as folder:
            root = Path(folder)
            (root / "twilight-reading.png").write_bytes(
                (ROOT / "twilight-reading.png").read_bytes())
            gate = root / "gate.sh"
            gate.write_text("#!/bin/bash\nprintf 'Simulated blocked scan' >&2\nexit 7\n")
            document = root / "blocked-report.pdf"
            document.write_bytes(b"%PDF-1.4\nsynthetic blocked PDF\n")
            original = (
                'FileManager.default.homeDirectoryForCurrentUser\n'
                '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")'
            )
            self.assertEqual(native.count(original), 1)
            native = native.replace(original, 'URL(fileURLWithPath: "' + str(gate) + '")')
            harness = native + "\n" + progress + "\n" + preference.replace(
                "import Foundation\n", ""
            ) + f"""
let app = NSApplication.shared
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
DispatchQueue.main.async {{
    delegate.application(app, open: [URL(fileURLWithPath: "{document}")])
}}
func verifyAttention(_ tries: Int = 0) {{
    let panels = app.windows.compactMap {{ $0 as? ScanProgressPanel }}
    if let panel = panels.first,
       panel.cancelButton.title == "Close",
       panel.stageLabel.stringValue == "Attention required — opening stopped" {{
        precondition(panel.isVisible, "Blocked scan must stay visible after its warning")
        precondition(panel.filenameLabel.stringValue == "blocked-report.pdf")
        precondition(panel.activeScansLabel.stringValue == "Active scans: 0")
        // The button immediately terminates NSApplication, so mark the
        // planned acknowledgement before performing the actual Close action.
        print("PASS: user explicitly closed the failed scan window", flush: true)
        panel.cancelButton.performClick(nil)
        return
    }}
    precondition(tries < 100, "The blocked scan never entered attention state")
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {{
        verifyAttention(tries + 1)
    }}
}}
DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {{
    verifyAttention()
}}
app.run()
"""
            swift = root / "attention.swift"
            swift.write_text(harness)
            binary = root / "attention"
            subprocess.run(["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                            str(swift), "-o", str(binary)], check=True, timeout=90)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: failure warning retains the progress window", result.stdout)
            self.assertIn("PASS: user explicitly closed the failed scan window", result.stdout)

    def test_success_and_hidden_progress_remain_unchanged(self):
        source = (ROOT / "brave-pdf-opener.swift").read_text(encoding="utf-8")
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("guard ScanProgressPreference.isEnabled() else {", source)
        self.assertIn("attentionRequired = false\n            panel?.orderOut(nil)", source)
        self.assertIn("self.pending.isEmpty && self.pendingSuccessNotifications == 0 && !self.attentionRequired", source)
        self.assertIn("python3 test-native-attention-required.py -v", ci)
        self.assertIn("python3 test-native-hidden-scan-progress.py", ci)
        self.assertIn("python3 test-native-cancellation.py", ci)


if __name__ == "__main__":
    unittest.main()
