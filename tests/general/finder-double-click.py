#!/usr/bin/env python3
"""Exercise Finder-style Launch Services PDF delivery without changing defaults.

An explicit "open -a" routes a file through the same macOS open-documents
Apple event that Finder uses for a double-click. The actual Finder gesture
requires an interactive desktop and is covered by the manual checklist.
"""
import json
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "brave-pdf-opener.swift"
PROGRESS_SOURCE = ROOT / "scan-progress-view.swift"
PREFERENCE_SOURCE = ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift"
HANDLER_READER = ROOT / "identify-pdf-handler.swift"
SCRIPT_ANCHOR = (
    'FileManager.default.homeDirectoryForCurrentUser\n'
    '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/scan-and-open.py")'
)


def run(*args, **kwargs):
    return subprocess.run(args, check=True, timeout=90, **kwargs)


def main():
    assert os.uname().sysname == "Darwin", "Requires macOS Launch Services"
    source = SOURCE.read_text(encoding="utf-8")
    assert source.count(SCRIPT_ANCHOR) == 1, "The native scan-gate entry point changed"
    assert "func application(_ application: NSApplication, open urls: [URL])" in source
    assert "startScan(path)" in source or "startQueuedScans()" in source

    with tempfile.TemporaryDirectory(prefix="pdf-finder-open-") as tmp:
        root = Path(tmp).resolve()
        app = root / "Finder PDF Test.app"
        executable = app / "Contents/MacOS/TestOpener"
        resources = app / "Contents/Resources"
        executable.parent.mkdir(parents=True)
        resources.mkdir()
        (resources / "twilight-reading.png").write_bytes(
            (ROOT / "twilight-reading.png").read_bytes()
        )
        receipt = root / "scan-receipt.txt"
        gate = root / "fake-clean-gate.py"
        gate.write_text(
            "import pathlib, sys\n"
            "pathlib.Path(" + repr(str(receipt)) + ").write_text("
            "sys.argv[1] + '\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        # The real UI and queue remain unchanged. Only the direct Python scan
        # target is replaced with a harmless receipt writer in this test app.
        harness = root / "finder-opener.swift"
        harness.write_text(
            source.replace(SCRIPT_ANCHOR, "URL(fileURLWithPath: " + json.dumps(str(gate)) + ")") + "\n" +
            PROGRESS_SOURCE.read_text(encoding="utf-8") + "\n" +
            PREFERENCE_SOURCE.read_text(encoding="utf-8").replace("import Foundation\n", ""),
            encoding="utf-8",
        )
        info = {
            "CFBundleExecutable": "TestOpener",
            "CFBundleIdentifier": "org.pdfmagic.opener.finder-ci",
            "CFBundleName": "PDF Magic Finder Test",
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

        # Observe the PDF association without modifying it. The CI app is
        # explicitly selected, never installed as the default.
        reader = root / "IdentifyPDFHandler"
        run("/usr/bin/xcrun", "swiftc", "-parse-as-library",
            str(HANDLER_READER), "-o", str(reader))

        def current_handler():
            result = subprocess.run([str(reader)], capture_output=True,
                                    text=True, timeout=10)
            return (result.returncode, result.stdout.strip())

        original_handler = current_handler()
        document = root / "Finder test – spaces & Unicode.PDF"
        document.write_bytes(
            b"%PDF-1.4\n"
            b"1 0 obj\n<</Type /Catalog /Pages 2 0 R>>\nendobj\n"
            b"2 0 obj\n<</Type /Pages /Kids [] /Count 0>>\nendobj\n"
            b"trailer\n<</Root 1 0 R>>\n%%EOF\n"
        )

        # This sends a real Launch Services open-documents event to a real
        # packaged application, unlike directly calling its delegate method.
        # Supplying -a avoids touching the user's PDF default association.
        run("/usr/bin/open", "-a", str(app), str(document))
        deadline = time.monotonic() + 25
        while not receipt.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert receipt.exists(), "Launch Services did not deliver the PDF to the scan gate"
        # Launch Services may decompose Unicode when constructing file URLs.
        # File identity and NFC-equivalent names must survive that conversion.
        import unicodedata
        delivered = Path(receipt.read_text(encoding="utf-8").strip())
        assert delivered.is_file() and delivered.samefile(document), (
            "The open-documents event selected a different PDF"
        )
        assert unicodedata.normalize("NFC", delivered.name) == unicodedata.normalize(
            "NFC", document.name
        ), "The open-documents event changed the requested PDF filename"
        assert current_handler() == original_handler, (
            "The test changed the registered default PDF handler"
        )
        print("PASS: Launch Services delivered a Finder-style PDF open event to the scan gate.")
        print("PASS: The original path and registered default PDF handler were preserved.")


if __name__ == "__main__":
    main()
