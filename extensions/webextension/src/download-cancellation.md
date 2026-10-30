# Detect cancelled browser downloads (opener-0675)

`subscribeToDownloadCancellations(downloadsApi, onCancelled, { onError }?)`
is a passive adapter using the existing normalized browser download events.
Importing it never registers listeners. An explicitly opted-in, trusted caller
must verify the browser's current optional downloads permission before
subscribing, and stop monitoring upon revocation.

Only downloads.onChanged with `error.current` exactly `USER_CANCELED`
emits an immutable `{ kind: "cancelled", id }` notification. A generic
`interrupted` state, `USER_SHUTDOWN`, network errors and file errors are not
user cancellation. The onErased event deletes a history entry, not a download.
Created and erased events only reset the ID's suppression state for reuse.

Notifications contain solely the numeric browser download ID, never URLs,
paths, filenames, headers, cookies, referrers, bytes, browser danger metadata
or scan claims. Duplicate notices are bounded to 256 remembered IDs.
Unsubscribing clears the cache and detaches every listener; callback failures
produce only a generic path-free error. The module never calls downloads.cancel.

Detection does not authorize a PDF scan, cancellation of a native scan or
opening a file. The shipped background remains inactive. Native scanner
freshness, verified scanning, quarantine, file integrity and user-selected
application settings are preserved. No browser permission or setting changes.

Tests: `extensions/webextension/tests/download-cancellation.test.mjs`
is discovered by the existing `npm test`/`scanner-tests` CI suite.

Reference: https://developer.chrome.com/docs/extensions/reference/api/downloads
