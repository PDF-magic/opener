# PDF Magic Opener

Safe & reliable document launcher for macOS.

Scan PDFs locally with ClamAV before opening them in Brave, with a Twilight Sparkle reading animation while the check runs. The included Finder action also scans other file types before opening them in their assigned app.

## Art

`twilight-reading.png` [comes from](https://desuarchive.org/mlp/thread/28772083/#28800531) /r/ Anon

## Installation and usage

Install local malware scanning for the existing **Allow and Open** Finder action and native PDF opening (requires Homebrew and Apple command line tools):

```sh
bash install-allow-and-open.sh
```

Double-click PDFs to scan them locally with ClamAV and open them in Brave. A small Twilight Sparkle reading loop appears immediately while the scan runs, with the document name and an animated progress bar. Repeated clicks on the same document during a scan open only one copy; the window closes when the check finishes. The default PDF application becomes `~/Applications/PDF Magic Opener.app`, which runs the scan before handing the file to Brave. Both **Allow and Open** Finder entry points use the same scan gate; other selected file types use their assigned application after scanning.

The scan progress window has a **Cancel** button. Cancelling stops active scans, discards queued requests, and never opens or unquarantines cancelled files. Native scanner subprocesses run in isolated process groups and are terminated and reaped on cancellation, including when they ignore graceful termination. Finder and command-line scanning are unchanged.

Different documents can scan concurrently, with a maximum of **two active scans**. The native opener dispatches requests in arrival order, queues excess documents, and starts the next queued document when a slot becomes free. The Python scan gate also uses two private advisory lock slots under `~/Library/Application Support/Studio/allow-and-open/scan-slots/` so independent Finder and native-app invocations respect the same limit. Waiting requests do not bypass scanning or quarantine; slots are released even if a scanner process exits unexpectedly. The scan-count limit is fixed and does not change the user's existing scan settings.

Detection, scan errors, timeouts, encrypted inputs, exceeded scan limits, or signatures not checked within 48 hours stop opening and preserve quarantine. Files are checked for changes during scanning. App bundles are scanned recursively; links outside a bundle stop opening. Standalone PDFs have no opener-configured file or extracted-data size limit and allow up to 30 minutes for scanning. ClamAV's own approximately 2 GB per-file engine limit still blocks opening if exceeded; unlimited configured PDF scanning may require substantial CPU, memory, and temporary disk. Other files and app-bundle contents retain the 512 MB per-file and 1 GB total scan limits and a three-minute timeout. A clean scan means no threat was detected, not guaranteed safety. Files are never uploaded.

Each accepted native PDF open request also has an in-memory `ScanRequest.requestTimestamp` (`Date`) set when the open event is accepted. Repeated events for the same resolved file retain the original request timestamp. This field is not logged or persisted, and is distinct from the scan time used in the clean-file cache.

For integrations that already know a download's originating URL, the Python scan request supports optional `source_url` metadata via `ScanRequest.from_path(path, source_url=...)` or `scan_and_open(path, scanner, source_url=...)`. Local Finder and native opens leave it unset. The URL is not fetched, submitted to ClamAV, logged, or persisted, and does not change the path, cache, or safety checks.

Each accepted scan request records the **intended destination application** and request time in a separate local `~/Library/Application Support/Studio/allow-and-open/scan-requests.sqlite3` database (mode `0600`). PDFs target Brave (`com.brave.Browser`), opening an application bundle targets that named `.app`, and other files use the macOS default handler (`system-default` until macOS chooses an app). The record contains neither the requested file path nor file contents. If recording fails or the database path is a symlink, opening stops without bypassing scanning or removing quarantine. This request log is separate from the 90-day clean-scan cache.

Completed clean scans are cached locally for **90 days from the last successful scan** in `~/Library/Application Support/Studio/allow-and-open/clean-scan-cache.sqlite3`. The cache stores only SHA-256 hashes and scan timestamps, not file contents or paths. A matching hash under the same scanning policy skips another ClamAV scan even if a document is renamed or its filesystem timestamps change; standalone PDFs use separate cache keys so earlier size-limited scans cannot substitute for unlimited scans. the hash covers the complete file bytes, **including PDF metadata embedded in the file**, or the contents and relative paths of an application bundle. File bytes and filesystem identities (including members of application bundles) are checked across hashing and scanning, then checked again after quarantine removal immediately before launch. Byte-identical replacements also block opening. Quarantine removal can change filesystem change timestamps without altering file contents; that expected change alone does not invalidate the final check. Changed contents or identities, expired records, scan failures, or an unreadable cache require a new clean scan. The 48-hour malware-signature freshness gate is still checked every time. Verified clean-scan results include the ClamAV engine version from the scan that established the verdict. Cached results reuse that version, while legacy cache records report an unknown engine rather than misattributing a current one.

Concurrent requests with identical bytes and the same scan policy coordinate through a local advisory lock. A waiting request rechecks its file contents and the clean-cache entry, reusing only a verified clean scan; changed files and unsuccessful scans must be checked anew or blocked. Bounded, private per-policy lock stripes remain on disk to avoid races with processes already waiting on a lock. Each request still performs its own final content check before opening.

Scanner failures identify the request number and use a fixed, path-free reason; raw ClamAV output, source filenames, and exception text are not recorded in scan diagnostics. The selected path is still passed to ClamAV and the destination application when required, and the native scan progress window may temporarily display the filename.

**Security trade-off:** newly published ClamAV signatures will not rescan unchanged content that is already cached clean until the 90-day period expires. Delete `clean-scan-cache.sqlite3` while the opener is not running to force a new scan of every file. Caching does not make a clean verdict a guarantee of safety.

**Launch errors:** After successful malware and integrity checks, `scan_and_open` creates an immutable `CleanScanResult(status="clean", from_cache=...)` independent of launching. A failed destination launch still reports an error and a nonzero CLI exit status, but raises `LaunchFailedError` with the completed `scan_result` attached for callers. The verified 90-day clean scan cache remains valid, subject to existing signature freshness, file integrity and expiry checks, so retrying an unsuccessful launch does not automatically rescan. Incomplete or blocked scans never produce a clean result.

**Launch/scan separation:** `scan-and-open.py` verifies a file and passes clean requests to `file_launcher.py`, which owns the destination application selection. The scanner contains no browser bundle identifier. To retain existing behavior, the launcher currently opens PDFs in Brave (`com.brave.Browser`) and other files or application bundles through the system's default macOS application handlers. This task does not introduce new application preferences or change the user's installed associations. The installer deploys both modules together.

Each accepted scan attempt also records the **requesting scan-gate application** (PDF Magic Opener or the Allow and Open Finder Quick Action) and timestamp in a separate `scan_request_applications` table of the private `scan-requests.sqlite3` database. Direct calls to `scan-and-open.py` default to **Command Line**; integrations can set `PDF_MAGIC_REQUESTING_APPLICATION`. This identifies the scan entry point, **not** the external app that originally opened a document through macOS Launch Services. Requester records contain no document paths, types, or contents. Logging failures stop the requested opening. Delete the request database while the opener is stopped to clear both requester and destination history.

**Native application launching:** After the scan gate approves a file, verifies unchanged contents, and completes quarantine handling, `file_launcher.py` invokes an installed Swift helper using macOS `NSWorkspace` APIs rather than `/usr/bin/open`. PDFs still target Brave by bundle identifier; other files use their system default app, and `.app` bundles launch as applications. A missing target or failed launch stops opening without fallback. Existing installations must rerun the installer to build the helper.

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
python3 test-launch-results.py
python3 test-scan-concurrency.py
python3 test-brave-pdf-opener.py
```

## File lifecycle contract

A file request has seven defined, case-sensitive lifecycle states: `queued`,
`scanning`, `analyzing`, `blocked`, `ready`, `opening`, and `completed`.
The transitions are:

| Current state | Allowed next states |
| --- | --- |
| `queued` | `scanning`, `blocked` |
| `scanning` | `analyzing`, `blocked` |
| `analyzing` | `ready`, `blocked` |
| `ready` | `opening`, `blocked` |
| `opening` | `completed`, `blocked` |
| `blocked` | None (terminal) |
| `completed` | None (terminal) |

The normal success path advances through the five active stages to completion.
Failures, cancellation, or a revoked decision can block a request at any
nonterminal stage. A blocked or completed request cannot resume; retry with a
new queued request. Self-transitions and skipped stages are invalid.
`file_lifecycle.py` provides `FileState`, immutable `VALID_TRANSITIONS`,
`can_transition`, and a validating `transition_state` helper. This module
defines the contract for future integrations; it does **not** change existing
ClamAV scanning, opening behavior, cache, quarantine, or user configuration.

## Scan result vocabulary (section 1.3)

The canonical terminal result names are defined in `scan_results.py` as
`ScanResultStatus`. They are stable, case-sensitive strings for callers to
consume as scan-result reporting is added. These definitions do **not** change
the current scanner's exit codes, quarantine handling, or opening behavior.

| Result | Meaning |
| --- | --- |
| `clean` | All required checks completed successfully with no detected threat or blocking condition; **not** a guarantee of safety. |
| `malwareDetected` | The scanner positively identified malware. |
| `suspiciousStructure` | The file structure appeared suspicious or malformed, without a confirmed malware identification. |
| `encrypted` | Encryption prevented a required inspection of the file's contents. |
| `incompleteScan` | The scanner skipped required content or could not confirm that inspection was complete. |
| `scanFailed` | A scanner execution, scanner prerequisite, or other scan operation failed. |
| `scanTimedOut` | The configured time allowed for scanning expired. |
| `fileChanged` | The input changed between verification and the end of scanning. |
| `fileTooLarge` | The input exceeded a configured or scanner-enforced size limit. |
| `cancelled` | The scan request was cancelled before completion. |

**Fail-closed contract:** only `clean` may permit further opening processing;
every other result blocks opening and leaves quarantine in place. A cancellation,
scan error, or partial scan must never be treated as `clean`.

## Scan-request origins

Each scan request records three origin flags (Finder, browser, or other desktop application) in a separate local `scan-request-origins.jsonl` file in the same application-support directory. Finder Quick Actions label their requests explicitly; native PDF opens use the macOS open-event sender when available. Unidentified senders leave all three flags false rather than guessing. The file contains timestamps and origin flags only—never document names, paths, contents, or scan verdicts. It is separate from the clean-verdict cache and can be deleted while the opener is not running. Existing installations must rerun the installer to add Finder attribution. Origin logging is informational and cannot change whether the scanner blocks a file.

## Tooling

| File | Purpose |
| --- | --- |
| `install-allow-and-open.sh` | Install the scan gate, native app, Finder action integration, and signature update agent |
| `brave-pdf-opener.swift` | Native PDF open handler with scan progress and duplicate-open prevention |
| `allow-and-open.sh` | Shared shell entry point for the scan gate |
| `scan-and-open.py` | Validate signatures, scan files, preserve quarantine on failure, and open clean files |
| `record-scan-origin.py` | Record three local scan-request origin flags without retaining file identities |
| `update-malware-signatures.sh` | Refresh the local ClamAV signature database |
| `set-brave-pdf-default.swift` | Set the default PDF handler to the supplied app, or Brave when no app is supplied |
| `test-scan-and-open.py` | Verify scan-gate behavior with a substitute scanner |
| `test-scan-concurrency.py` | Verify concurrent scans, queued requests, and shared process limits |
| `test-brave-pdf-opener.py` | Verify native progress visibility and duplicate-open handling |

The installer requires an existing **Allow and Open** Quick Action at `~/Library/Services/Allow and Open.workflow` and Brave Browser. Run the commands above from this repository's root.

For compatibility with existing installations, runtime scripts and signatures remain in `~/Library/Application Support/Studio/allow-and-open`, logs remain in `~/Library/Logs/Studio`, and the app and LaunchAgent keep their `local.studio` identifiers. The installer safely relocates a verified legacy `Open PDFs in Brave.app` bundle to `PDF Magic Opener.app` when upgrading. This change names the application; Brave remains the PDF destination until browser selection is implemented.

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
