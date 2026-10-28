#!/usr/bin/env python3
"""Verify a failed native scan visibly identifies the requested PDF and explains failure.

The real native completion handler is executed with a harmless nonzero scan stub.
Only NSAlert.runModal is replaced with assertions to avoid hanging headless CI.
"""
from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent
native = (ROOT / "brave-pdf-opener.swift").read_text()
assert native.count("alert.runModal()") == 1, "Production must present an actual modal warning"
assert native.count("if let failure = failure {") == 1
assert native.count("makeScanFailureAlert(") == 2, "Only the factory and error branch may use it"

classes = native.split("@main\nstruct PDFMagicOpenerEntry {", 1)[0]
classes += "\n" + (ROOT / "scan-progress-view.swift").read_text()
classes += "\n" + (ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text().replace(
    "import Foundation\n", ""
)
classes = classes.replace(
    "alert.runModal()",
    """
    precondition(alert.alertStyle == .critical, "A failed safety check must use a critical alert")
    precondition(alert.messageText == "PDF could not be opened", "The failure heading must be explicit")
    precondition(alert.informativeText.contains("File: selected alias – report.pdf"),
                 "Failure must identify the original requested alias")
    precondition(alert.informativeText.contains("safety scan or destination handoff failed"),
                 "Failure must explain why opening stopped")
    precondition(!alert.informativeText.contains("resolved.pdf"),
                 "Never replace the alias with the canonical scanner filename")
    if ProcessInfo.processInfo.environment["SCAN_TEST_EMPTY"] == "1" {
        precondition(alert.informativeText.contains("returned no additional error details"),
                     "Empty scanner stderr must yield a useful explanation")
    } else {
        precondition(alert.informativeText.contains("Simulated ClamAV signature failure"),
                     "Failure must preserve the scanner-provided diagnostic")
    }
    print("PASS: native failure alert identifies requested PDF and explains the error")
    """,
    1,
)

with tempfile.TemporaryDirectory(prefix="opener-failure-presentation-") as directory:
    work = Path(directory)
    (work / "twilight-reading.png").write_bytes((ROOT / "twilight-reading.png").read_bytes())
    gate = work / "gate.sh"
    gate.write_text(
        "#!/bin/bash\n"
        'if [ "$SCAN_TEST_EMPTY" = "1" ]; then exit 7; fi\n'
        "printf 'Simulated ClamAV signature failure\\n' >&2\n"
        "exit 7\n"
    )
    resolved = work / "resolved.pdf"
    resolved.write_bytes(b"%PDF-1.4\nsynthetic\n")
    alias = work / "selected alias – report.pdf"
    alias.symlink_to(resolved)
    original = (
        'FileManager.default.homeDirectoryForCurrentUser\n'
        '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")'
    )
    assert classes.count(original) == 1, "Native scan gate must be isolated from installed scanner"
    classes = classes.replace(original, 'URL(fileURLWithPath: "' + str(gate) + '")')

    harness = classes + """
let app = NSApplication.shared
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
DispatchQueue.main.async {
    delegate.application(app, open: [URL(fileURLWithPath: "__REQUESTED_ALIAS__")])
}
app.run()
""".replace("__REQUESTED_ALIAS__", str(alias))
    swift = work / "failure.swift"
    swift.write_text(harness)
    binary = work / "failure"
    subprocess.run(["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                    str(swift), "-o", str(binary)], check=True)

    for empty in (False, True):
        environment = os.environ.copy()
        environment["SCAN_TEST_EMPTY"] = "1" if empty else "0"
        run = subprocess.run([str(binary)], env=environment,
                             capture_output=True, text=True, timeout=15)
        assert run.returncode == 0, run.stdout + run.stderr
        assert "PASS: native failure alert identifies requested PDF and explains the error" in run.stdout, (
            run.stdout + run.stderr
        )
    print("PASS: scanner diagnostics and empty stderr produce actionable native failure alerts.")
