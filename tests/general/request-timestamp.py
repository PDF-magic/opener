#!/usr/bin/env python3
"""Exercise native request timestamps with duplicate events and a harmless scan stub."""
from pathlib import Path
import subprocess
import tempfile

source = (Path(__file__).resolve().parents[2] / "brave-pdf-opener.swift").read_text()
classes = source.split("@main\nstruct PDFMagicOpenerEntry {")[0]
classes += "\n" + (Path(__file__).resolve().parents[2] / "scan-progress-view.swift").read_text()
classes += "\n" + (Path(__file__).resolve().parents[2] / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text().replace("import Foundation\n", "")

with tempfile.TemporaryDirectory(prefix="opener-timestamp-test-") as directory:
    root = Path(directory)
    (root / "twilight-reading.png").write_bytes(
        (Path(__file__).resolve().parents[2] / "twilight-reading.png").read_bytes()
    )
    gate = root / "gate.sh"
    calls = root / "calls"
    document = root / "first.pdf"
    document.touch()
    alias = root / "alias.pdf"
    alias.symlink_to(document)
    second = root / "second.pdf"
    second.touch()
    gate.write_text(f'#!/bin/bash\nprintf "%s\\n" "$1" >> "{calls}"\nsleep 1\n')

    original = classes
    classes = classes.replace(
        'FileManager.default.homeDirectoryForCurrentUser\n'
        '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")',
        f'URL(fileURLWithPath: "{gate}")',
    )
    assert classes != original, "Native scan-gate path could not be substituted"

    harness = classes + f'''
let app = NSApplication.shared
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
let document = URL(fileURLWithPath: "{document}")
let alias = URL(fileURLWithPath: "{alias}")
let second = URL(fileURLWithPath: "{second}")
DispatchQueue.main.async {{
    let before = Date()
    delegate.application(app, open: [document, alias, document])
    guard let first = delegate.scanRequests[document.path],
          first.requestTimestamp >= before,
          first.requestTimestamp <= Date(),
          delegate.scanRequests.count == 1 else {{
        fatalError("The first accepted request must have an arrival timestamp")
    }}
    let firstTime = first.requestTimestamp
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {{
        delegate.application(app, open: [alias, second, document])
        guard let retained = delegate.scanRequests[document.path],
              let later = delegate.scanRequests[second.path],
              delegate.scanRequests.count == 2,
              retained.requestTimestamp == firstTime,
              later.requestTimestamp >= firstTime,
              later.requestTimestamp <= Date() else {{
            fatalError("Duplicates must retain the first timestamp; new requests need their own")
        }}
    }}
}}
app.run()
'''
    swift = root / "test.swift"
    swift.write_text(harness)
    binary = root / "opener"
    subprocess.run(["/usr/bin/xcrun", "swiftc", str(swift), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=15)
    assert sorted(calls.read_text().splitlines()) == sorted([str(document), str(second)]), (
        "Repeated or aliased open events must launch one scan per resolved file"
    )
    print("PASS: request timestamps are per-accepted-file, stable on duplicates, and session-only.")
