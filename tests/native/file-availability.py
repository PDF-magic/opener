#!/usr/bin/env python3
"""Test native cloud download-state policy with synthetic macOS metadata."""
from pathlib import Path
import subprocess
import tempfile

swift = (Path(__file__).resolve().parents[2]s[2] / "launch-scanned-file.swift").read_text()
start = swift.index("func downloadStatusAllowsOpen(")
end = swift.index("func launch(", start)
policy = swift[start:end]

with tempfile.TemporaryDirectory(prefix="pdf-download-policy-") as directory:
    root = Path(directory)
    source = root / "download-policy.swift"
    source.write_text("import Foundation\n" + policy + """
@main
struct DownloadPolicyTests {
    static func main() {
        precondition(downloadStatusAllowsOpen(isUbiquitous: false,
            downloadingStatus: nil, isDownloading: nil))
        precondition(downloadStatusAllowsOpen(isUbiquitous: nil,
            downloadingStatus: nil, isDownloading: nil))
        precondition(downloadStatusAllowsOpen(isUbiquitous: true,
            downloadingStatus: .downloaded, isDownloading: false))
        precondition(downloadStatusAllowsOpen(isUbiquitous: true,
            downloadingStatus: .current, isDownloading: false))
        precondition(!downloadStatusAllowsOpen(isUbiquitous: true,
            downloadingStatus: .notDownloaded, isDownloading: false))
        precondition(!downloadStatusAllowsOpen(isUbiquitous: true,
            downloadingStatus: .notDownloaded, isDownloading: true))
        precondition(!downloadStatusAllowsOpen(isUbiquitous: true,
            downloadingStatus: nil, isDownloading: nil))
        precondition(!downloadStatusAllowsOpen(isUbiquitous: true,
            downloadingStatus: .downloaded, isDownloading: true))
        print("PASS: native macOS PDF download-state policy")
    }
}
""")
    binary = root / "download-policy"
    subprocess.run(["/usr/bin/xcrun", "swiftc", "-parse-as-library",
                    "-warnings-as-errors", str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True, timeout=15)
