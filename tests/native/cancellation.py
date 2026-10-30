#!/usr/bin/env python3
"""Exercise the native Cancel button against two active and one queued job."""
from pathlib import Path
import os
import subprocess
import tempfile

source = Path(__file__).with_name("brave-pdf-opener.swift").read_text()
classes = source.split("@main\nstruct PDFMagicOpenerEntry {")[0]
classes += "\n" + Path(__file__).with_name("scan-progress-view.swift").read_text()
classes += "\n" + (Path(__file__).parent / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text().replace("import Foundation\n", "")
with tempfile.TemporaryDirectory(prefix="opener-native-cancel-") as directory:
    root = Path(directory)
    (root / "twilight-reading.png").write_bytes(
        Path(__file__).with_name("twilight-reading.png").read_bytes())
    gate = root / "gate.sh"
    started = root / "started"
    documents = [root / f"selected-{index}.pdf" for index in range(3)]
    for doc in documents:
        doc.write_bytes(b"%PDF-1.4\nNative cancel test")
    gate.write_text(
        "#!/bin/bash\n"
        f'printf "%s:%s\\n" "$1" "$$" >> "{started}"\n'
        "exec /bin/sleep 30\n"
    )
    classes = classes.replace(
        'FileManager.default.homeDirectoryForCurrentUser\n'
        '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/allow-and-open.sh")',
        f'URL(fileURLWithPath: "{gate}")'
    )
    urls = ", ".join(f'URL(fileURLWithPath: "{doc}")' for doc in documents)
    harness = classes + f"""
let app = NSApplication.shared
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
DispatchQueue.main.async {{
    delegate.application(app, open: [{urls}])
    guard let panel = app.windows.compactMap({{ $0 as? NSPanel }}).first,
          let cancel = panel.contentView?.subviews.compactMap({{ $0 as? NSButton }})
              .first(where: {{ $0.title == "Cancel" }}) else {{
        fatalError("Scanning must display an actionable Cancel button")
    }}
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {{
        guard let data = FileManager.default.contents(atPath: "{started}"),
              let text = String(data: data, encoding: .utf8),
              text.split(whereSeparator: {{ $0.isNewline }}).count == 2 else {{
            fatalError("Two active scans must start before cancellation")
        }}
        guard let progress = panel as? ScanProgressPanel,
              progress.activeScansLabel.stringValue == "Active scans: 2",
              progress.activeScansLabel.accessibilityLabel() == "Active scans: 2" else {{
            fatalError("Only two launched scans, not the queued third document, should count as active")
        }}
        cancel.performClick(nil)
    }}
}}
app.run()
"""
    source_file = root / "cancel-test.swift"
    source_file.write_text(harness)
    binary = root / "cancel-test"
    subprocess.run(["/usr/bin/xcrun", "swiftc", str(source_file), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=20)
    entries = [line.rsplit(":", 1) for line in started.read_text().splitlines()]
    assert len(entries) == 2, "Cancel must discard queued work"
    assert {path for path, _ in entries} == {str(doc) for doc in documents[:2]}
    for _, pid_string in entries:
        try:
            os.kill(int(pid_string), 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("An active native scan survived cancellation")
    print("PASS: Cancel terminates active scan processes and discards queued work.")
