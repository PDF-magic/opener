# Avoid scanning partially written downloads (opener-0684)

`preflightCompletedDownloadForScan(downloadsApi, permissionsApi, completion)`
is a passive, one-shot prerequisite for **future** download-to-scan
coordination. It does not start scanning, create native messages or install
listeners on import. A separately reviewed user-authorized integration must
provide an ID-only `{ kind: "completed", id }` event from the existing
`subscribeToDownloadCompletions` adapter.

Before any metadata lookup the preflight observes downloads permission
revocation, then requires an explicitly positive current
`permissions.contains({ permissions: ["downloads"] })`. It queries
`downloads.search({ id })` **only** for that exact download and rejects
missing, ambiguous, revoked, interrupted, queued, paused, resumable or
deleted results. A current `state: "complete"`, an existing regular
browser download record, non-temporary filename, and valid transfer byte
counts are required. Known `totalBytes` must exactly equal positive
`bytesReceived`; `totalBytes: -1` (unknown length) requires a positive
received count and a complete browser state. Common partial-download
suffixes (`.part`, `.crdownload`, `.partial`, `.download`, `.tmp` and
`.icloud`) are refused. On refusal, rejection or missing permissions the
result is `null`, never a request to scan a partial file.

A successful preflight returns only an immutable, path-free
`{ id, transferComplete: true, scanVerified: false, authorizesScan: false,
authorizesOpen: false }` record. No filenames, absolute paths, URLs,
cookies, headers, browser history or file contents are emitted or stored.
Browser completion remains *untrusted metadata*: it cannot prove a local file
is unchanged or free of an external writer. Before any future native scan
dispatch, the trusted coordinator **must additionally verify the canonical
file identity and stability**, then enforce all existing ClamAV signature
freshness, full-byte scanning, integrity, quarantine and selected-application
checks. This implementation does not wire a scan to any browser event.

The shipped WebExtension background remains inert. This task changes no
scanner path, browser permission, native protocol, UI setting or user
customization. Ten regression tests in
`tests/download-scan-preflight.test.mjs` are picked up by the existing
WebExtensions `npm test` stage of required `scanner-tests` CI.
