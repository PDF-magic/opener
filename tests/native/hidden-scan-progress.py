#!/usr/bin/env python3
"""Check hidden native progress still dispatches a scan, without touching real user defaults."""

from pathlib import Path
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
native = (ROOT / "brave-pdf-opener.swift").read_text().split(
    "@main\nstruct PDFMagicOpenerEntry {", 1)[0]
preference = (ROOT / "PDFMagicOpenerApp" / "ScanProgressPreference.swift").read_text()
progress = (ROOT / "scan-progress-view.swift").read_text()

with tempfile.TemporaryDirectory(prefix="opener-hidden-progress-") as work:
    root = Path(work)
    marker = root / "scanner-was-run"
    pdf = root / "scanned.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    gate = root / "scan.py"
    gate.write_text(
        "import pathlib, sys, time\n"
        "pathlib.Path(" + repr(str(marker)) + ").write_text("
        "sys.argv[1] + '\\n', encoding='utf-8')\n"
        "time.sleep(1)\n"
    )
    suite = "local.studio.pdf-magic-opener.test.hidden." + uuid.uuid4().hex
    old = (
        'FileManager.default.homeDirectoryForCurrentUser\n'
        '            .appendingPathComponent("Library/Application Support/Studio/allow-and-open/scan-and-open.py")'
    )
    assert native.count(old) == 1
    native = native.replace(old, f'URL(fileURLWithPath: "{gate}")')
    expected = "guard ScanProgressPreference.isEnabled() else {"
    assert native.count(expected) == 1, "Only the progress display should read this preference"
    native = native.replace(
        expected, "guard ScanProgressPreference.isEnabled(defaults: isolatedDefaults) else {"
    )
    native = native.replace(
        "final class PDFOpener: NSObject, NSApplicationDelegate {",
        f'''let isolatedDefaults = UserDefaults(suiteName: "{suite}")!
final class PDFOpener: NSObject, NSApplicationDelegate {{'''
    )
    harness = native + "\n" + preference.replace("import Foundation\n", "") + "\n" + progress
    harness += f"""
let app = NSApplication.shared
isolatedDefaults.set(false, forKey: ScanProgressPreference.key)
let delegate = PDFOpener()
app.delegate = delegate
app.setActivationPolicy(.accessory)
DispatchQueue.main.async {{
    delegate.application(app, open: [URL(fileURLWithPath: "{pdf}")])
    precondition(app.windows.compactMap {{ $0 as? ScanProgressPanel }}.isEmpty,
                 "Disabled progress must not create a window")
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) {{
        precondition(FileManager.default.fileExists(atPath: "{marker}"),
                     "Hiding progress must never bypass scan dispatch")
        precondition(app.windows.compactMap {{ $0 as? ScanProgressPanel }}.isEmpty,
                     "Progress must stay hidden while the scanner runs")
        isolatedDefaults.removePersistentDomain(forName: "{suite}")
        print("PASS: native progress is hidden while the scanner still starts")
    }}
}}
app.run()
"""
    source = root / "hidden-progress.swift"
    source.write_text(harness)
    binary = root / "hidden-progress"
    subprocess.run(["/usr/bin/xcrun", "swiftc", "-warnings-as-errors",
                    str(source), "-o", str(binary)], check=True)
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=20)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "PASS: native progress is hidden while the scanner still starts" in run.stdout, run.stdout
    assert marker.read_text().strip() == str(pdf), "The actual requested file must enter scan gate"
    print(run.stdout.strip())
