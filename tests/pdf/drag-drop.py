#!/usr/bin/env python3
"""Exercise a PDF-to-application drop through explicit Launch Services targeting.

CI delivers the same open-documents event as an application-icon drop; a
literal Finder or Dock pointer drag remains a manual test.
"""
import json
from pathlib import Path
import plistlib
import shlex
import subprocess
import sys
import tempfile
import time
import unicodedata


ROOT = Path(__file__).resolve().parents[2]
APP_SOURCE = ROOT / "brave-pdf-opener.swift"
PROGRESS_SOURCE = ROOT / "scan-progress-view.swift"
PREFERENCE_SOURCE = ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift"
HANDLER_SOURCE = ROOT / "identify-pdf-handler.swift"
SCAN_GATE = (
    'FileManager.default.homeDirectoryForCurrentUser\n'
    '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")'
)

EXPLICIT_APP_OPEN = """
import AppKit
import Foundation

guard CommandLine.arguments.count == 3 else { exit(2) }
let application = URL(fileURLWithPath: CommandLine.arguments[1])
let document = URL(fileURLWithPath: CommandLine.arguments[2])
let configuration = NSWorkspace.OpenConfiguration()
configuration.activates = false
var finished = false
var failure: String?
NSWorkspace.shared.open([document], withApplicationAt: application,
                        configuration: configuration) { _, error in
    failure = error?.localizedDescription
    finished = true
}
let deadline = Date().addingTimeInterval(20)
while !finished && Date() < deadline {
    _ = RunLoop.current.run(mode: .default, before: Date().addingTimeInterval(0.05))
}
guard finished && failure == nil else {
    fputs("Explicit application open failed or timed out\\n", stderr)
    exit(1)
}
"""


def run(*command):
    subprocess.run(command, check=True, timeout=90)


def test_drop_handoff():
    if sys.platform != "darwin":
        raise RuntimeError("This integration test requires macOS Launch Services.")

    source = APP_SOURCE.read_text(encoding="utf-8")
    if source.count(SCAN_GATE) != 1:
        raise AssertionError("The native scan-gate entry point changed.")
    if "func application(_ application: NSApplication, open urls: [URL])" not in source:
        raise AssertionError("The app no longer accepts document open events.")

    with tempfile.TemporaryDirectory(prefix="pdf-app-drop-") as directory:
        root = Path(directory)
        app = root / "PDF Magic Drop Test.app"
        executable = app / "Contents/MacOS/DropTest"
        resources = app / "Contents/Resources"
        executable.parent.mkdir(parents=True)
        resources.mkdir()
        (resources / "twilight-reading.png").write_bytes(
            (ROOT / "twilight-reading.png").read_bytes()
        )

        receipt = root / "scan-receipt.txt"
        gate = root / "receipt-only-scan.sh"
        gate.write_text(
            "#!/bin/bash\nset -euo pipefail\n"
            "printf '%s\\n' \"$1\" > " + shlex.quote(str(receipt)) + "\n",
            encoding="utf-8",
        )
        harness = root / "drop-opener.swift"
        harness.write_text(
            source.replace(SCAN_GATE, "URL(fileURLWithPath: "
                           + json.dumps(str(gate)) + ")") + "\n" +
            PROGRESS_SOURCE.read_text(encoding="utf-8") + "\n" +
            PREFERENCE_SOURCE.read_text(encoding="utf-8").replace("import Foundation\n", ""),
            encoding="utf-8",
        )

        info = {
            "CFBundleExecutable": "DropTest",
            "CFBundleIdentifier": "org.pdfmagic.opener.drop-ci",
            "CFBundleName": "PDF Magic Drop Test",
            "CFBundlePackageType": "APPL",
            "CFBundleVersion": "1",
            "LSUIElement": True,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "PDF document",
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
                "LSItemContentTypes": ["com.adobe.pdf"],
            }],
        }
        with (app / "Contents/Info.plist").open("wb") as stream:
            plistlib.dump(info, stream)
        run("/usr/bin/xcrun", "swiftc", "-parse-as-library", str(harness), "-o", str(executable))
        run("/usr/bin/codesign", "--force", "--sign", "-", str(app))

        reader = root / "IdentifyPDFHandler"
        run("/usr/bin/xcrun", "swiftc", "-parse-as-library",
            str(HANDLER_SOURCE), "-o", str(reader))

        def current_default():
            result = subprocess.run([str(reader)], capture_output=True,
                                    text=True, timeout=10)
            return result.returncode, result.stdout.strip()

        original_default = current_default()
        document = root / "Dropped file – spaces & Unicode.PDF"
        document.write_bytes(
            b"%PDF-1.4\n"
            b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
            b"2 0 obj\n<</Type /Pages /Kids [] /Count 0>>\nendobj\n"
            b"trailer\n<</Root 1 0 R>>\n%%EOF\n"
        )

        opener = root / "ExplicitAppOpen.swift"
        opener.write_text(EXPLICIT_APP_OPEN, encoding="utf-8")
        launcher = root / "ExplicitAppOpen"
        run("/usr/bin/xcrun", "swiftc", str(opener), "-o", str(launcher))

        # NSWorkspace targets this app directly, not the default PDF handler.
        run(str(launcher), str(app), str(document))
        deadline = time.monotonic() + 25
        while not receipt.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        if not receipt.exists():
            raise AssertionError("The explicit app open did not reach its scan gate.")
        delivered = Path(receipt.read_text(encoding="utf-8").strip())
        if not delivered.is_file() or not delivered.samefile(document):
            raise AssertionError("The explicit app open selected a different PDF.")
        if unicodedata.normalize("NFC", delivered.name) != unicodedata.normalize(
                "NFC", document.name):
            raise AssertionError("The explicit app open changed the PDF filename.")
        if current_default() != original_default:
            raise AssertionError("The drop test changed the default PDF handler.")
        print("PASS: Explicit PDF-to-app delivery reached the native scan gate.")
        print("PASS: PDF identity and default PDF association were preserved.")


if __name__ == "__main__":
    test_drop_handoff()
