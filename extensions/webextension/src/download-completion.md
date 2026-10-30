# Download completion notifications (opener-0673)

`src/download-completion.js` exports `subscribeToDownloadCompletions(downloadsApi,
onCompleted, { onError }?)`. This is an **explicitly invoked**, browser-neutral,
passive adapter built on the already reviewed `subscribeToDownloadEvents`
normalizer. It does not install listeners on import, grant permissions, wire the
currently inert background script, or monitor downloads by default. A trusted
future caller must separately verify the optional `downloads` browser grant,
user consent and lifecycle before calling it; no browser-global API is read.

Only a `downloads.onChanged` event with `state.current` **exactly** `"complete"`
emits a frozen `{ kind: "completed", id }` notification. A created event, a
filename/danger-only change, a previous state of `complete`, incomplete or
interrupted state, and malformed browser IDs cannot establish completion. The
adapter suppresses repeated completed notices per browser download ID, releases
IDs on `onCreated` and numeric `onErased`, and bounds its in-memory deduplication
to 256 recent IDs. Unsubscribing detaches all three existing normalized event
listeners and clears the ID cache. There is no persistence, URL, path,
referrer, filename, credential, download content or browsing history retention.

**Completion is a browser-reported transfer state, not a clean ClamAV verdict,
verified file integrity, an authorization to open the PDF, or proof that the
download is a PDF.** Even a `danger: safe` value cannot override the separate
mandatory scanner freshness, full scan, quarantine and user-chosen application
checks. This module does not touch native messaging, scanners, file openers or
any user settings. It must not trigger automatic opening.

The new `tests/download-completion.test.mjs` is discovered by the existing
WebExtensions `npm test` command in required `scanner-tests` CI. The tests
cover actual `onChanged` event state detection, duplicate suppression,
identifier reuse, malformed or interrupted events, privacy, listener cleanup,
registration failures and consumer error isolation.
