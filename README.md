# PDF Magic Opener

Safe & reliable document launcher for macOS.

Scan PDFs locally with ClamAV before opening them in a configurable application (Brave by default), with a Twilight Sparkle reading animation while the check runs. The included Finder action also scans other file types before opening them in their assigned app.

## Art

`twilight-reading.png` [comes from](https://desuarchive.org/mlp/thread/28772083/#28800531) /r/ Anon

## Installation and usage

Install local malware scanning for the existing **Allow and Open** Finder action and native PDF opening (requires Homebrew and Apple command line tools):

```sh
bash install-allow-and-open.sh
```

Double-click PDFs to scan them locally with ClamAV and open them in the selected application (Brave by default). A small Twilight Sparkle reading loop appears immediately while the scan runs, with the document name and an animated progress bar. Repeated clicks on the same document during a scan open only one copy; the window closes when the check finishes. The default PDF application becomes `~/Applications/PDF Magic Opener.app`, which runs the scan before handing the file to the selected application. The installer now checks that macOS actually registered PDF Magic Opener after requesting the default-handler change; a mismatch or unreadable association fails installation rather than reporting success. Both **Allow and Open** Finder entry points use the same scan gate; other selected file types use their assigned application after scanning.

The scan progress window has a **Cancel** button. Cancelling stops active scans, discards queued requests, and never opens or unquarantines cancelled files. Native scanner subprocesses run in isolated process groups and are terminated and reaped on cancellation, including when they ignore graceful termination. Finder and command-line scanning are unchanged.

Different documents can scan concurrently, with a maximum of **two active scans**. The native opener dispatches requests in arrival order, queues excess documents, and starts the next queued document when a slot becomes free. The Python scan gate also uses two private advisory lock slots under `~/Library/Application Support/Studio/allow-and-open/scan-slots/` so independent Finder and native-app invocations respect the same limit. Waiting requests do not bypass scanning or quarantine; slots are released even if a scanner process exits unexpectedly. The scan-count limit is fixed and does not change the user's existing scan settings.

Detection, scan errors, timeouts, encrypted inputs, exceeded scan limits, or signatures not checked within 48 hours stop opening and preserve quarantine. Files are checked for changes during scanning. App bundles are scanned recursively; links outside a bundle stop opening. Standalone PDFs have no opener-configured file or extracted-data size limit and allow up to 30 minutes for scanning. ClamAV's own approximately 2 GB per-file engine limit still blocks opening if exceeded; unlimited configured PDF scanning may require substantial CPU, memory, and temporary disk. Other files and app-bundle contents retain the 512 MB per-file and 1 GB total scan limits and a three-minute timeout. A clean scan means no threat was detected, not guaranteed safety. Files are never uploaded.

Each accepted native PDF open request also has an in-memory `ScanRequest.requestTimestamp` (`Date`) set when the open event is accepted. Repeated events for the same resolved file retain the original request timestamp. This field is not logged or persisted, and is distinct from the scan time used in the clean-file cache.

For integrations that already know a download's originating URL, the Python scan request supports optional `source_url` metadata via `ScanRequest.from_path(path, source_url=...)` or `scan_and_open(path, scanner, source_url=...)`. Local Finder and native opens leave it unset. The URL is not fetched, submitted to ClamAV, logged, or persisted, and does not change the path, cache, or safety checks.

Each accepted scan request records the **intended destination application** and request time in a separate local `~/Library/Application Support/Studio/allow-and-open/scan-requests.sqlite3` database (mode `0600`). PDFs target Brave (`com.brave.Browser`), opening an application bundle targets that named `.app`, and other files use the macOS default handler (`system-default` until macOS chooses an app). The record contains neither the requested file path nor file contents. If recording fails or the database path is a symlink, opening stops without bypassing scanning or removing quarantine. This request log is separate from the 90-day clean-scan cache.

When PDF Magic Opener exits during a native scan, it closes the scan gate's parent-lifetime pipe. The scan is cancelled and the ClamAV process group is stopped; abandoned scans cannot cache a new clean result, clear quarantine, or open a file. Finder and direct command-line scans retain their prior behavior.

Completed clean scans are cached locally for **90 days from the last successful scan** in `~/Library/Application Support/Studio/allow-and-open/clean-scan-cache.sqlite3`. The cache stores SHA-256 hashes, scan timestamps, and optional scanner-engine and signature-database versions, not file contents or paths. A matching hash under the same scanning policy skips another ClamAV scan even if a document is renamed or its filesystem timestamps change; standalone PDFs use separate cache keys so earlier size-limited scans cannot substitute for unlimited scans. the hash covers the complete file bytes, **including PDF metadata embedded in the file**, or the contents and relative paths of an application bundle. File bytes and filesystem identities (including members of application bundles) are checked across hashing and scanning, then checked again after quarantine removal immediately before launch. Byte-identical replacements also block opening. Quarantine removal can change filesystem change timestamps without altering file contents; that expected change alone does not invalidate the final check. Changed contents or identities, expired records, scan failures, or an unreadable cache require a new clean scan. The 48-hour malware-signature freshness gate is still checked every time. Verified clean-scan results include the ClamAV engine version from the scan that established the verdict. Cached results reuse that version, while legacy cache records report an unknown engine rather than misattributing a current one.

The immutable clean-scan receipt also reports `signature_database_version`: ClamAV `main`, `daily`, and optional `bytecode` revisions read from installed `.cvd`/`.cld` headers. Cached results preserve these original revisions and the scanner-engine version. Missing, ambiguous, changing, or legacy version metadata is reported as `None`, not guessed; no source filenames or file contents are stored with this metadata.

Concurrent requests with identical bytes and the same scan policy coordinate through a local advisory lock. A waiting request rechecks its file contents and the clean-cache entry, reusing only a verified clean scan; changed files and unsuccessful scans must be checked anew or blocked. Bounded, private per-policy lock stripes remain on disk to avoid races with processes already waiting on a lock. Each request still performs its own final content check before opening.

Scanner failures identify the request number and use a fixed, path-free reason; raw ClamAV output, source filenames, and exception text are not recorded in scan diagnostics. The selected path is still passed to ClamAV and the destination application when required, and the native scan progress window may temporarily display the filename.

**Security trade-off:** newly published ClamAV signatures will not rescan unchanged content that is already cached clean until the 90-day period expires. Delete `clean-scan-cache.sqlite3` while the opener is not running to force a new scan of every file. Caching does not make a clean verdict a guarantee of safety.

**Launch errors:** After successful malware and integrity checks, `scan_and_open` creates an immutable `CleanScanResult(status="clean", from_cache=...)` independent of launching. A failed destination launch still reports an error and a nonzero CLI exit status, but raises `LaunchFailedError` with the completed `scan_result` attached for callers. The verified 90-day clean scan cache remains valid, subject to existing signature freshness, file integrity and expiry checks, so retrying an unsuccessful launch does not automatically rescan. Incomplete or blocked scans never produce a clean result.

**Unavailable selected PDF application:** When a configured browser is missing or cannot open PDFs, the macOS opener displays an `Opening stopped` warning explaining that the selected PDF application is unavailable or not PDF-capable. Install the selected application or change `~/Library/Application Support/Studio/allow-and-open/target-app.txt` to an installed PDF-capable application. If the opt-in system-default-browser choice cannot be resolved, check the default browser in macOS System Settings. If the native verification tool is unavailable, reinstall PDF Magic Opener. A browser that disappears after verification results in a separate explanation that scanning succeeded but launching failed. Diagnostics never reveal document paths, never silently switch browsers, and never bypass malware scanning or quarantine checks.

**Detect a changed macOS PDF default:** PDF Magic Opener does not silently reclaim the system PDF association after another application becomes the default. To check the current association against PDF Magic Opener's bundle ID without modifying any settings, run the installed `"$HOME/Library/Application Support/Studio/allow-and-open/detect-pdf-handler-change"` utility. It returns **0** if PDF Magic Opener is still the default, **2** if another application now owns the association (and names its bundle ID), or **1** if the default cannot be determined. Each invocation re-reads macOS Launch Services, so changes made between checks are detected. This read-only check does not continually monitor in the background, change the selected browser, or open a PDF. Reinstall the opener to deploy the utility; see the existing instructions below if you want to restore PDF Magic Opener as the system's PDF handler.

**PDF application support:** Before releasing quarantine or opening a verified clean PDF, including a clean cache hit, the launcher checks whether macOS Launch Services registers the chosen application as capable of opening PDFs. Safari (`com.apple.Safari`) is also supported when its installed bundle is executable and its Apple signature verifies, even if Safari does not advertise PDF-handler registration. Missing, unsupported, or unverifiable destinations fail closed. To select Safari, write `com.apple.Safari` to `~/Library/Application Support/Studio/allow-and-open/target-app.txt`, then use the existing scan-and-open workflow. Reinstall to deploy the native check. Brave remains the default and existing user choices are not overwritten.

**Launch/scan separation:** `scan-and-open.py` verifies a file and passes clean requests to `file_launcher.py`, which owns the destination application selection. The scanner contains no browser bundle identifier. To retain existing behavior, the launcher currently opens PDFs in Brave (`com.brave.Browser`) and other files or application bundles through the system's default macOS application handlers. This task does not introduce new application preferences or change the user's installed associations. The installer deploys both modules together.

Each accepted scan attempt also records the **requesting scan-gate application** (PDF Magic Opener or the Allow and Open Finder Quick Action) and timestamp in a separate `scan_request_applications` table of the private `scan-requests.sqlite3` database. Direct calls to `scan-and-open.py` default to **Command Line**; integrations can set `PDF_MAGIC_REQUESTING_APPLICATION`. This identifies the scan entry point, **not** the external app that originally opened a document through macOS Launch Services. Requester records contain no document paths, types, or contents. Logging failures stop the requested opening. Delete the request database while the opener is stopped to clear both requester and destination history.

**Bundle-ID verification:** A registered PDF target is accepted only if its macOS application bundle still exists, its identity matches the requested bundle identifier, and the bundle executable is available. Missing, stale, or mismatched app registrations stop opening without another application fallback.

**External-drive PDFs:** Finder and native open events accept ordinary mounted-volume file URLs (including names containing spaces or Unicode), then resolve them to local paths and apply the same ClamAV, integrity, quarantine, and configured PDF-target checks as internal files. When macOS grants a security-scoped file URL, the opener retains that access throughout queued and running scans and releases it on completion, cancellation, or termination. A disconnected or unreadable drive blocks opening rather than falling back to an unscanned copy. No external drive is copied to the internal disk by the opener.

**iCloud Drive PDFs:** Locally accessible PDF files in iCloud Drive follow the same scan, content-integrity, quarantine, and selected-application checks as any other local PDF. Use the file's normal Finder path (including paths under `~/Library/Mobile Documents/com~apple~CloudDocs/`); no special browser or destination configuration is needed. A cloud-only document that is not available as a local file cannot be opened by this workflow. The opener does not explicitly download or synchronize cloud files. Existing local file access, scan failure, and quarantine restrictions still apply.

**Recursive launch protection:** PDF Magic Opener is the scan gate, not a PDF destination. The configured PDF target cannot be its own bundle identifier. Both Python handoff and native macOS launching independently reject that destination; the native helper also refuses a PDF without an explicitly selected target, since the system default PDF handler may point back to PDF Magic Opener. Default-handler launches that would resolve back to the opener are refused. Other installed PDF destinations, user preferences, and non-PDF default handlers are unchanged.

**Incomplete cloud downloads:** Before hashing or scanning a PDF, the macOS launcher checks native download-state metadata. Cloud-only iCloud placeholders, PDFs still downloading, and files whose local availability cannot be verified do **not** launch a browser. The scan gate rechecks availability after scanning (including cache hits) and immediately before the native macOS launch to detect cloud eviction. Finder-style `.pdf.icloud` placeholder paths are rejected without scanning. Reopen the requested PDF once it has fully downloaded locally; the opener does not download it, wait indefinitely, or alter the configured PDF target. Reinstall to deploy the updated native helper.

**Already-running browsers:** If the selected PDF browser is already open, macOS receives the approved file through the same explicit `NSWorkspace` application handoff, rather than launching a second browser by design. The macOS CI regression uses a temporary browser-like `.app` and verifies the open event reaches its existing process. This does not bypass malware scanning, change application preferences, or require a real browser installation.

**Native application launching:** After the scan gate approves a file, verifies unchanged contents, and completes quarantine handling, `file_launcher.py` invokes an installed Swift helper using macOS `NSWorkspace` APIs rather than `/usr/bin/open`. PDFs still target Brave by bundle identifier; other files use their system default app, and `.app` bundles launch as applications. A missing target or failed launch stops opening without fallback. Existing installations must rerun the installer to build the helper.

Browser integrations may optionally pass `--browser-download-id <identifier> <file-path>` to attach a validated session-only download identifier to a scan request. Regular Finder, native and direct-path opens leave it unset. It is never logged, persisted, or used to change the file scanned or the selected PDF application.

The installer downloads ClamAV's official signatures and installs a user LaunchAgent to check for updates every four hours while logged in. To update manually:

```sh
bash update-malware-signatures.sh
```

The installer keeps the original workflow beside `document.wflow` as `document.wflow.before-brave`. To restore direct Brave opening without this scan gate:

```sh
swift set-pdf-default-handler.swift
```

Opening a file explicitly through another app bypasses this opener. Scanner details: [ClamAV scanning documentation](https://docs.clamav.net/manual/Usage/Scanning.html).

Verify the scan gate with:

```sh
python3 test-scan-and-open.py
python3 test-target-app.py
python3 test-launch-results.py
python3 test-scan-concurrency.py
python3 test-brave-pdf-opener.py
```

## Restore PDF Magic Opener as the default PDF handler

When the installer detects that another application is the current default for
PDF files, it **offers to restore PDF Magic Opener**. Answer `y` or `yes`
to approve that change; any other response keeps the existing association.
If the installer is running non-interactively, it leaves the association
untouched and explains how to run it interactively. An unavailable or invalid
Launch Services handler lookup never triggers an automatic change. If PDF
Magic Opener is already the default, no prompt or setter call is necessary.

Restoration affects only macOS' default PDF association; the separate app
chosen to receive clean PDFs in `target-app.txt` remains unchanged. Re-running
the installer gives the same restoration offer without bypassing any scanning,
quarantine, or integrity checks.

## Inspect the registered macOS PDF handler

To see which application macOS currently has registered as the default for
PDF documents, reinstall to deploy the read-only helper and run:

```sh
"$HOME/Library/Application Support/Studio/allow-and-open/identify-pdf-handler"
```

The command prints the **bundle identifier** returned by macOS Launch Services
for the PDF content type (for example, `local.studio.brave-pdf-opener` if
PDF Magic Opener is the current handler, or `com.apple.Preview`).
If no handler can be identified, it prints a fixed error and exits unsuccessfully
rather than guessing. This reports the **system PDF association**, not the
separately configured app that receives clean PDFs or the default web browser.
It neither changes file associations nor opens any file or application.

### Current default PDF-handler status

To display whether **PDF Magic Opener** is the current default for PDF files,
and which application is registered if it is not, run:

```sh
python3 "$HOME/Library/Application Support/Studio/allow-and-open/pdf-handler-status.py"
```

Reinstall to deploy this command. The installer also prints the current status
after macOS completes any required default-handler confirmation. A successful
lookup reports the current application bundle identifier; an unavailable or
unverifiable association produces a fixed error and an unsuccessful exit rather
than a guessed status.

The command **only reads** the macOS PDF association using the separately
installed `identify-pdf-handler` helper. It does not open a PDF, change the
default PDF association, change the browser receiving scanned PDFs, or modify
user preferences.

## Make PDF Magic Opener the default PDF application

After installing, double-click **Make PDF Magic Opener Default.command** in
`~/Applications` to explicitly make PDF Magic Opener the macOS PDF handler.
You can also invoke that same user action from Terminal:

```sh
bash "$HOME/Applications/Make PDF Magic Opener Default.command"
```

This action verifies the installed PDF Magic Opener application's identity,
executable, and PDF support before asking macOS to change the association.
It reports an error if the application is missing or macOS refuses the change.
It does not open any PDF, run a scan, or modify your selected post-scan browser
(`target-app.txt`). It runs **only when invoked**, not whenever a PDF opens.
Installation still registers the opener as before; this action allows you to
restore it later if another application takes over.

## PDF target application

For a comparison of viewer capabilities, browser-specific settings, and
launch requirements, see [Browser PDF viewer differences](docs/browser-pdf-viewers.md).

The PDF target is a macOS application **bundle identifier**, not a shell
command or executable path. The default is `com.brave.Browser`. After
installing, edit
`~/Library/Application Support/Studio/allow-and-open/target-app.txt` to use a
different installed application; for example, Preview:

```sh
printf '%s\n' 'com.apple.Preview' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

To open scanned PDFs in **Google Chrome**, use its bundle identifier instead:

```sh
printf '%s\n' 'com.google.Chrome' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

To follow your **macOS default web browser** automatically (instead of a fixed
bundle identifier), opt in by writing `system-default-browser` to the same file:

```sh
printf '%s\n' 'system-default-browser' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

Reinstall the opener first to deploy the browser resolver. It queries macOS'
default handler for HTTPS URLs without opening a URL or changing the browser
preference. Each PDF request pins the resolved application's bundle ID before
scanning. The existing PDF-capability and installed-app checks still apply;
an unavailable, unsupported, or self-referential default browser blocks opening
without falling back to the default PDF handler (which may be PDF Magic Opener).

Chrome must be installed and registered with macOS as a PDF-capable application.
The launcher verifies the selected bundle and PDF registration before opening,
and never substitutes another browser when verification fails.

To open scanned PDFs in **Arc** instead, use Arc's macOS bundle identifier:

```sh
printf '%s\n' 'company.thebrowser.Browser' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

Arc's PDF viewer may not be registered as a macOS PDF handler. The
preflight accepts only the installed Arc bundle with a working executable and
a valid Browser Company signature (team S6N382Y83G); missing or untrusted
installations stop opening. The ClamAV and quarantine checks still run, and
Brave remains the default unless the user explicitly selects Arc.

To open scanned PDFs in **Chromium** (the open-source browser, distinct from
Google Chrome), select its macOS bundle identifier:

```sh
printf '%s\n' 'org.chromium.Chromium' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

Chromium must be installed and registered as a PDF-capable application with
macOS. The existing launcher verifies that specific bundle, then passes the
unchanged local PDF to Chromium only after ClamAV and file-integrity checks
succeed. A missing or unregistered Chromium installation blocks opening rather
than falling back to Chrome, Brave, or another browser. Existing user selections
are not overwritten.

To open verified PDFs in **Vivaldi**, select its application bundle identifier:

```sh
printf '%s\n' 'com.vivaldi.Vivaldi' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

Vivaldi has a built-in PDF viewer but may not register with Launch Services as
a PDF handler. The opener accepts Vivaldi only when the selected installed app
has the exact Vivaldi bundle identifier and an executable; missing or mismatched
apps fail closed. Every PDF still requires the existing malware scan, integrity
checks, and quarantine policy before the pinned Vivaldi destination can launch.
This setting does not change the system's default browser or PDF association.

To open approved PDFs in **Opera** (the standard macOS release), select
its bundle identifier without changing the system's default browser:

```sh
printf '%s\n' 'com.operasoftware.Opera' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

Opera must be installed. The launcher accepts a registered PDF-capable Opera
bundle, or a verified, executable Opera bundle with Opera's genuine code
signature when Launch Services does not list it as a PDF handler. An absent,
impostor, unsigned, or unusable Opera installation fails closed; it does not
fall back to another app. Opera GX is a separate application and is not
covered by this Opera-specific exception. ClamAV scanning and the existing
file-integrity and quarantine checks always precede launching.

To open approved PDFs in Mozilla Firefox instead, use Firefox's bundle ID:

```sh
printf '%s\n' 'org.mozilla.firefox' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

Firefox has a built-in PDF viewer but may not register itself as a PDF handler
with macOS. The launcher accepts an installed Firefox application only when
its bundle identity, executable, and Mozilla Developer ID signature are verified; other applications must
still be registered PDF handlers. The usual ClamAV, quarantine, and
file-integrity checks still apply before Firefox is launched.

An optional **fallback PDF application** can be configured separately. For
example, use Preview only if the selected browser cannot be verified or fails
to launch after a successful scan:

```sh
printf '%s\n' 'com.apple.Preview' > "$HOME/Library/Application Support/Studio/allow-and-open/fallback-app.txt"
```

The fallback must be an installed, independently verified PDF-capable macOS
application, specified by bundle identifier (not a command, executable, or
`system-default-browser` shortcut). If the fallback setting is missing,
there is **no automatic fallback**; a malformed or symlinked setting blocks
PDF opening. A fallback is never attempted after detection, scan errors,
an unavailable cloud file, failed integrity checks, or quarantine errors.
On a failed preferred-app launch, the fallback must already have passed PDF
capability verification before quarantine removal, and the file is rechecked
before its second launch attempt. The request audit retains the preferred
destination and adds a fallback destination entry when used. Existing
settings survive reinstallations unchanged. Non-PDF documents and application
bundles are unaffected.

The setting survives reinstallations. An absent setting falls back to Brave
for existing installations; an invalid, unreadable or symlinked setting stops
PDF opening instead of silently choosing an application. The setting affects
only PDF files; other files and application bundles keep their macOS default
behavior. Scanning, signature freshness, content verification, quarantine,
and clean-scan caching still gate every PDF before launch.

To open scanned PDFs in **Microsoft Edge (stable)**, select its macOS bundle identifier:

```sh
printf '%s\\n' 'com.microsoft.edgemac' > "$HOME/Library/Application Support/Studio/allow-and-open/target-app.txt"
```

Edge must be installed and registered with macOS as a PDF-capable application.
The existing launcher verifies its bundle identity, executable, and PDF
registration before releasing quarantine or opening a clean file. If Edge is
missing or unsupported, the request stops without trying another browser;
non-PDF associations and the existing scanning safeguards are unchanged.

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

**Detection metadata:** Unique ClamAV `FOUND` signatures appear as `ScanResult.detection_names` in scanner order, without paths or unrelated diagnostic text. Blocked failures expose `error.scan_result`; clean or cached scan results have an empty detection-name tuple. Names are in-memory only and never bypass the scanning or quarantine gate.

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
| `set-pdf-default-handler.swift` | Set the default PDF handler to the supplied app, or Brave when no app is supplied |
| `test-scan-and-open.py` | Verify scan-gate behavior with a substitute scanner |
| `test-target-app.py` | Verify target selection, fail-closed settings, and preservation on reinstall |
| `test-scan-concurrency.py` | Verify concurrent scans, queued requests, and shared process limits |
| `test-brave-pdf-opener.py` | Verify native progress visibility and duplicate-open handling |

The installer requires an existing **Allow and Open** Quick Action at `~/Library/Services/Allow and Open.workflow`; Brave Browser is needed when using the default target. Run the commands above from this repository's root.

For compatibility with existing installations, runtime scripts and signatures remain in `~/Library/Application Support/Studio/allow-and-open`, logs remain in `~/Library/Logs/Studio`, and the app and LaunchAgent keep their `local.studio` identifiers. The installer safely relocates a verified legacy `Open PDFs in Brave.app` bundle to `PDF Magic Opener.app` when upgrading. The configurable PDF handoff preserves the established application identity and scan controls.

## License

Licensed under the [GNU Affero General Public License v3.0](LICENSE).
