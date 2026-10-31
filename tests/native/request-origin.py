#!/usr/bin/env python3
"""Compile and check native event-source classification on the macOS CI runner."""
from pathlib import Path
import subprocess
import tempfile

repository = Path(__file__).resolve().parents[2]
source = (repository / 'brave-pdf-opener.swift').read_text()
shared_preferences = repository / 'PDFMagicOpenerApp' / 'ScanProgressPreference.swift'
classes = source.split('final class PDFOpener: NSObject, NSApplicationDelegate {')[0]
assert 'func requestSource(forBundleIdentifier' in classes
with tempfile.TemporaryDirectory(prefix='pdf-origin-test-') as directory:
    root = Path(directory)
    harness = root / 'main.swift'
    harness.write_text(classes + '''
precondition(requestSource(forBundleIdentifier: "com.apple.finder") == "finder")
precondition(requestSource(forBundleIdentifier: "com.apple.Safari") == "browser")
precondition(requestSource(forBundleIdentifier: "com.brave.Browser") == "browser")
precondition(requestSource(forBundleIdentifier: "com.google.Chrome") == "browser")
precondition(requestSource(forBundleIdentifier: "org.mozilla.firefox") == "browser")
precondition(requestSource(forBundleIdentifier: "com.apple.Preview") == "desktop-application")
precondition(requestSource(forBundleIdentifier: nil) == "unknown")
print("PASS: native Finder, browser, desktop-application, unknown origin classification")
''')
    binary = root / 'origin-check'
    # Compile against the same shared preference source as the installed helper.
    subprocess.run(['/usr/bin/xcrun', 'swiftc', str(harness), str(shared_preferences), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=15)
