# Scan PDFs Only download preference (opener-0728)

The shared WebExtensions configuration now has a **Scan PDFs Only** option
(`scanPdfsOnly`), defaulting to `true`. It is a **scope preference**, not a
permission to monitor downloads or open documents; the five existing active
capabilities remain disabled by default. Existing saved preferences are never
overwritten just because the setting was added.

A future reviewed, extension-owned download-settings page can explicitly
construct `createScanPdfsOnlySetting(root, store)` and call `load()`.
The accessible checkbox has a visible label and explanation. Its injected
store must supply asynchronous `readConfiguration()` and
`saveScanPdfsOnly(boolean)` operations, with the latter atomically modifying
**only** this key while preserving every other user preference. It confirms
the value through a fresh read after the save. Missing keys use the default
without writing; malformed storage, errors and unconfirmed writes fail closed
instead of claiming success. Only genuine trusted user changes initiate saves.
`clear()` and `dispose()` unbind stale controls and results.

`considerDownloadForScan(configuration, mimeRecord, filenameRecord)`
is a passive eligibility hint using the existing completed-download MIME and
filename detectors. It requires both independently permission-checked,
matching download ID records. PDF MIME catches misleading extensions;
a `.pdf` suffix with generic MIME is also considered. With the option on,
non-PDF browser hints are excluded. With it off, other downloads are
**considered for later native review**, not automatically scanned or opened.
Invalid, mismatched and hostile metadata cannot yield an eligibility result.

**Security and deployment limitation:** browser-declared MIME and filename
are never evidence of actual content. A disguised PDF may evade browser-side
PDF-only classification; no browser extension can guarantee universal
interception. Production use still requires separately reviewed explicit
consent, the optional downloads grant, an authenticated native coordinator,
canonical file identity/byte validation, complete ClamAV scanning with fresh
signatures, quarantine retention, fail-closed error handling and the user's
verified PDF application preference. Switching this preference off does not
enable support for scanning non-PDF file types or bypass any installed scanner
gate. The shipped background/popup and native host stay inactive. No browser
permissions, private paths, existing scanner settings, or launch behavior
change in this PR.

The dedicated Node suite is automatically discovered by the existing
`npm test` command in the required `scanner-tests` GitHub Actions job.
