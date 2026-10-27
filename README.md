# opener

Safe & reliable document launcher for macOS.

Scan PDFs locally with ClamAV before opening them in Brave, with a Twilight Sparkle reading animation while the check runs. The included Finder action also scans other file types before opening them in their assigned app.

## Installation and usage

Install local malware scanning for the existing **Allow and Open** Finder action and native PDF opening (requires Homebrew and Apple command line tools):

```sh
bash install-allow-and-open.sh
```

Double-click PDFs to scan them locally with ClamAV and open them in Brave. A small Twilight Sparkle reading loop appears immediately while the scan runs, with the document name and an animated progress bar. Repeated clicks on the same document during a scan open only one copy; the window closes when the check finishes. The default PDF application becomes `~/Applications/Open PDFs in Brave.app`, which runs the scan before handing the file to Brave. Both **Allow and Open** Finder entry points use the same scan gate; other selected file types use their assigned application after scanning.

Detection, scan errors, timeouts, encrypted inputs, exceeded scan limits, or signatures not checked within 48 hours stop opening and preserve quarantine. Files are checked for changes during scanning. App bundles are scanned recursively; links outside a bundle stop opening. Standalone PDFs have no opener-configured file or extracted-data size limit and allow up to 30 minutes for scanning. ClamAV's own approximately 2 GB per-file engine limit still blocks opening if exceeded; unlimited configured PDF scanning may require substantial CPU, memory, and temporary disk. Other files and app-bundle contents retain the 512 MB per-file and 1 GB total scan limits and a three-minute timeout. A clean scan means no threat was detected, not guaranteed safety. Files are never uploaded.

Completed clean scans are cached locally for **90 days from the last successful scan** in `~/Library/Application Support/Studio/allow-and-open/clean-scan-cache.sqlite3`. The cache stores only SHA-256 hashes and scan timestamps, not file contents or paths. A matching hash under the same scanning policy skips another ClamAV scan even if a document is renamed or its filesystem timestamps change; standalone PDFs use separate cache keys so earlier size-limited scans cannot substitute for unlimited scans. the hash covers the complete file bytes, **including PDF metadata embedded in the file**, or the contents and relative paths of an application bundle. A file is hashed again before opening, and changed contents, expired records, scan failures, or an unreadable cache require a new clean scan. The 48-hour malware-signature freshness gate is still checked every time.

**Security trade-off:** newly published ClamAV signatures will not rescan unchanged content that is already cached clean until the 90-day period expires. Delete `clean-scan-cache.sqlite3` while the opener is not running to force a new scan of every file. Caching does not make a clean verdict a guarantee of safety.

The installer downloads ClamAV's official signatures and installs a user LaunchAgent to check for updates every four hours while logged in. To update manually:

```sh
bash update-malware-signatures.sh
```

The installer keeps the original workflow beside `document.wflow` as `document.wflow.before-brave`. To restore direct Brave opening without this scan gate:

```sh
swift set-brave-pdf-default.swift
```

Opening a file explicitly through another app bypasses this opener. Scanner details: [ClamAV scanning documentation](https://docs.clamav.net/manual/Usage/Scanning.html).

Verify the scan gate with:

```sh
python3 test-scan-and-open.py
python3 test-brave-pdf-opener.py
```

## Tooling

| File | Purpose |
| --- | --- |
| `install-allow-and-open.sh` | Install the scan gate, native app, Finder action integration, and signature update agent |
| `brave-pdf-opener.swift` | Native PDF open handler with scan progress and duplicate-open prevention |
| `allow-and-open.sh` | Shared shell entry point for the scan gate |
| `scan-and-open.py` | Validate signatures, scan files, preserve quarantine on failure, and open clean files |
| `update-malware-signatures.sh` | Refresh the local ClamAV signature database |
| `set-brave-pdf-default.swift` | Set the default PDF handler to the supplied app, or Brave when no app is supplied |
| `test-scan-and-open.py` | Verify scan-gate behavior with a substitute scanner |
| `test-brave-pdf-opener.py` | Verify native progress visibility and duplicate-open handling |

The installer requires an existing **Allow and Open** Quick Action at `~/Library/Services/Allow and Open.workflow` and Brave Browser. Run the commands above from this repository's root.

For compatibility with existing installations, runtime scripts and signatures remain in `~/Library/Application Support/Studio/allow-and-open`, logs remain in `~/Library/Logs/Studio`, and the app and LaunchAgent keep their `local.studio` identifiers.

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
