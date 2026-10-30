# Detect renamed downloads (opener-0683)

`download-renames.js` is an opt-in, browser-neutral event observer. Importing
it has **no effect**. A trusted integration must first obtain explicit download
monitoring consent and the browser's optional `downloads` permission, then
call `subscribeToDownloadRenames(downloadsApi, onRenamed)`. Call the returned
idempotent unsubscribe function when monitoring stops or permission is revoked.

The observer tracks only numeric IDs of downloads seen in `in_progress`
state, using at most 256 IDs. For an active ID, it detects
`downloads.onChanged` events with distinct, nonempty
`filename.previous` and `filename.current` values. An initial filename
assignment does **not** count as a rename. Completion, interruption, erasure,
and a fresh `onCreated` for a reused ID stop previous tracking.

Only a frozen `{ kind: "renamed", id }` notice leaves the module. It does
not retain, log, forward, scan, read or open paths; the browser's previous and
current filenames exist only during the event callback. On error, any reported
error is generic and contains no browser-provided filename.

This signal indicates a browser-reported rename **during a download**, not a
validated PDF, a completed download, a scan verdict or authorization to open a
file. The independent completion, permission, scanner freshness, integrity,
quarantine, and safe-opening boundaries remain in force. A rename after the
transfer completed or before observation began cannot be inferred.

Regression tests: `node --test tests/download-renames.test.mjs`. The existing
WebExtensions `npm test` script includes the tests in required CI.
