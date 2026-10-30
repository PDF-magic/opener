# Download interruption notifications (opener-0674)

`src/download-interruption.js` exports
`subscribeToDownloadInterruptions(downloadsApi, onInterrupted, { onError }?)`.
This passive, explicitly invoked adapter reuses the existing
`subscribeToDownloadEvents` normalizer. A trusted caller must separately
verify effective optional `downloads` permission, user consent and lifecycle
before subscribing. Importing the module attaches no listeners and never
activates the intentionally inert background worker.

Only a browser `downloads.onChanged` event whose `state.current` is exactly
`"interrupted"` emits a frozen `{ kind: "interrupted", id }` notice. Other
event types, previous-only states, error-only updates, malformed IDs and
complete/in-progress states cannot imply interruption. Repeated notices
are suppressed for up to 256 recent IDs. An `"in_progress"` state signals
resumption and permits a later interruption; created/erased events reset
IDs for safe reuse. Unsubscribing is idempotent, clears the cache and
detaches every normalized event listener.

**An interruption is only a browser-reported download transfer state.**
It does not establish whether the user canceled, the network failed, the
file exists or the download is a PDF. No error reason, URL, filename,
credentials, cookies, content, scan verdict or browser history is retained
or forwarded. The module cannot retry, resume, cancel, scan, quarantine
or open any file. It does not change user preferences or mandatory ClamAV
signature freshness, complete scanning, file-integrity, quarantine and
safe application-handoff safeguards.

The existing WebExtensions `npm test` CI run discovers
`tests/download-interruption.test.mjs`. It covers state transitions,
duplicates, resumption, ID reuse, bounded memory, malformed records,
privacy, registration rollback, callback isolation and teardown.
