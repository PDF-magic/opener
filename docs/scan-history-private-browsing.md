# Private browsing and optional persistent scan history (opener-0917)

**Private and unknown browser contexts must never append optional scan history
by default, even if the user enables history for normal scanning.** Private
browser consent is separate from history consent and does not make private
sessions eligible for on-disk recording.

The optional browser-origin persistence entry point is
`store_browser_scan_metadata(..., browsing_context=..., history_enabled=...)`.
It defaults to **unknown context and disabled history**, and returns `False`
without creating or reading directories, SQLite databases, or entries in these
cases. A trusted native adapter may save a browser scan only after it
independently verifies a currently **regular** session and an affirmative
persistent-history setting, passing the exact
`BrowserScanContext.REGULAR` enum and `history_enabled=True`. Arbitrary
browser strings, truthy values, a previous browser grant, a private-session
opt-in, or a pre-existing database do not establish either precondition.
`BrowserScanContext.PRIVATE` and `UNKNOWN` always suppress persistence;
there is **no override to record private browsing** in this task.

This is a storage-boundary guard for a future trusted browser integration,
not activation of browser scanning or of history collection. Chromium and
Firefox manifests continue declaring `"incognito": "not_allowed"`; Safari
has its own user-controlled private-window behavior and is protected
independently by the storage guard. The shared extension background stays
inactive. The existing local scanner metadata writer remains unchanged for
nonbrowser callers; a future browser adapter must use this dedicated,
conservative browser-origin entry point rather than calling the local writer
directly. No active browser-to-history path exists today.

Persisted regular-session metadata still has the existing strict, private
SQLite schema: UTC time, terminal status, scanner version and effective
protection profile only. The guard never records URLs, PDF content, paths,
filenames, private-context flags or browser session identifiers. It neither
grants scan/open authorization nor changes scanner freshness, quarantine,
operational scan caches, Clear History, or other user customizations.

Portable CI tests use synthetic records to verify denial before any disk
access, unchanged existing history after private events, rejection of
unknown/untrusted browsing evidence, allowed explicitly opted-in regular
metadata, unchanged manifests and inactive browser background.
