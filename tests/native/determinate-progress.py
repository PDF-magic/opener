#!/usr/bin/env python3
"""Exercise measured batch completion without inventing per-file scan percentages."""

from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parent


class NativeDeterminateProgressTests(unittest.TestCase):
    def test_actual_request_completion_and_unknown_single_file_progress(self):
        native = (ROOT / "brave-pdf-opener.swift").read_text().split(
            "@main\nstruct PDFMagicOpenerEntry {", 1)[0]
        progress = (ROOT / "scan-progress-view.swift").read_text()
        preference = (ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text()
        self.assertIn("finishedRequests += 1", native)
        self.assertNotIn("ScanProgressPreference", native.split(
            "private func startQueuedScans()", 1)[1])
        with tempfile.TemporaryDirectory(prefix="opener-determinate-") as directory:
            root = Path(directory)
            (root / "twilight-reading.png").write_bytes(
                (ROOT / "twilight-reading.png").read_bytes())
            first = root / "first.pdf"
            second = root / "second.pdf"
            first.write_bytes(b"%PDF-1.4\n")
            second.write_bytes(b"%PDF-1.4\n")
            gate = root / "gate.sh"
            gate.write_text(
                "#!/bin/bash\n"
                f'printf started > "{root}/$(basename "$1").started"\n'
                f'while [ ! -f "{root}/$(basename "$1").released" ]; do sleep 0.05; done\n'
                "exit 0\n"
            )
            old_gate = (
                'FileManager.default.homeDirectoryForCurrentUser\n'
                '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")'
            )
            self.assertEqual(native.count(old_gate), 1)
            native = native.replace(old_gate, f'URL(fileURLWithPath: "{gate}")')
            suite = "local.studio.pdf-magic-opener.test.determinate." + uuid.uuid4().hex
            native = native.replace(
                "final class PDFOpener: NSObject, NSApplicationDelegate {",
                f'let isolatedDefaults = UserDefaults(suiteName: "{suite}")!\n'
                "final class PDFOpener: NSObject, NSApplicationDelegate {",
            )
            expected = "guard ScanProgressPreference.isEnabled() else {"
            self.assertEqual(native.count(expected), 1)
            native = native.replace(
                expected,
                "guard ScanProgressPreference.isEnabled(defaults: isolatedDefaults) else {",
            )
            harness = native + "\n" + preference.replace("import Foundation\n", "") + "\n" + progress
            harness += f"""
let app = NSApplication.shared
isolatedDefaults.set(true, forKey: ScanProgressPreference.key)
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
let first = URL(fileURLWithPath: "{first}")
let second = URL(fileURLWithPath: "{second}")

func poll(_ attempts: Int = 0, condition: @escaping () -> Bool,
          then continuation: @escaping () -> Void) {{
    if condition() {{ continuation(); return }}
    precondition(attempts < 160, "Timed out waiting for a real scan lifecycle event")
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {{
        poll(attempts + 1, condition: condition, then: continuation)
    }}
}}

DispatchQueue.main.async {{
    delegate.application(app, open: [first])
    guard let panel = app.windows.compactMap({{ $0 as? ScanProgressPanel }}).first else {{
        fatalError("Missing progress panel")
    }}
    precondition(panel.progressIndicator.isIndeterminate,
                 "One active PDF has no measurable per-file percentage")
    delegate.application(app, open: [second, second])
    precondition(!panel.progressIndicator.isIndeterminate,
                 "Two accepted requests have a measurable batch count")
    precondition(panel.progressIndicator.doubleValue == 0)
    precondition(panel.progressIndicator.maxValue == 2)
    poll(condition: {{
        FileManager.default.fileExists(atPath: "{first}.started")
            && FileManager.default.fileExists(atPath: "{second}.started")
    }}, then: {{
        // The first scan cannot finish until its explicitly supplied marker exists.
        try! Data().write(to: URL(fileURLWithPath: "{first}.released"))
        poll(condition: {{
            panel.progressIndicator.doubleValue == 1
                && !panel.progressIndicator.isIndeterminate
        }}, then: {{
            precondition(panel.progressIndicator.maxValue == 2)
            precondition(panel.progressIndicator.accessibilityLabel()
                         == "1 of 2 document requests processed")
            precondition(FileManager.default.fileExists(atPath: "{second}.released") == false,
                         "The second scan is still blocked while batch completion reads 1/2")
            isolatedDefaults.removePersistentDomain(forName: "{suite}")
            try! Data().write(to: URL(fileURLWithPath: "{second}.released"))
            print("PASS: only actual completed requests move the determinate batch bar")
        }})
    }})
}}
app.run()
"""
            harness_file = root / "test.swift"
            harness_file.write_text(harness)
            binary = root / "determinate"
            subprocess.run(
                ["/usr/bin/xcrun", "swiftc", "-warnings-as-errors", str(harness_file),
                 "-o", str(binary)],
                check=True,
            )
            run = subprocess.run(
                [str(binary)], capture_output=True, text=True, timeout=25,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn("PASS: only actual completed requests", run.stdout)


if __name__ == "__main__":
    unittest.main()
