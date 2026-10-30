# Avoid retaining browsing histories (opener-0595, §9.2)

PDF Magic Opener's shared browser extension must **not collect or retain a
browsing history**. It does not request the `history` permission, enumerate
browser visits, query past downloads, record visited sites or retain a timeline
of download URLs, source origins, referrers or tabs. No browser extension
history is sent to the native PDF scanner, diagnostic logs or remote services.

## Privacy-safe activity observation

The opt-in `subscribeToHistoryFreeDownloadActivity(downloadsApi, onActivity,
{ onError }?)` adapter exposes only one of three immutable signals:
`{ kind: "created"|"changed"|"erased", authorizesOpen: false }`. It discards
all browser-supplied download IDs, filenames, URL/referrer, timestamps,
tab identifiers, file bytes and prior metadata before calling `onActivity`.
The module stores **no per-download data, caches, event queues or timestamps**;
signals are reused instead of allocating records tied to individuals or
websites. Callers must not persist these activity signals into a chronology.

It wraps the existing, separately reviewed `subscribeToDownloadEvents`
adapter without changing that lower-level API for future scanner use. The
privacy-safe wrapper never grants permission, registers listeners on import,
or enables the existing inert background. Explicit subscription requires
a separately authorized caller; its idempotent unsubscribe detaches all
listeners and prevents post-unsubscribe delivery. Errors are isolated and
registration rolls back. Private browsing is separately restricted by
opener-0593; Safari private-context policy needs its own runtime review.

This is **not a complete browsing privacy guarantee for arbitrary future
callers**: they must not store data obtained directly from lower-level
browser downloads APIs, nor keep even anonymous timestamps that could form
a user activity history. A later active integration requires a separate
consent, no-retention and native scanner safety review.

The existing `permissions: []`, `host_permissions: []` and
`optional_permissions: ["downloads"]` do not authorize collection of
browsing history. No history, tabs, website origins, content scripts or
persistent extension storage are introduced by this task. Scanner freshness,
document integrity, quarantine and user-selected PDF application behavior
remain unchanged.

CI exercises anonymous event delivery and non-retention, rejection and
unsubscribe behavior, no browser-history grant and absence of runtime
history/storage calls, via the existing WebExtensions Node test suite.
