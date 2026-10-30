# Preserve the browser's native malware warnings (opener-0701)

The browser's own download danger/warning mechanism is **independent** of
PDF Magic Opener's ClamAV scanner. Native browser warnings must never be
dismissed, accepted, bypassed, cleared, downgraded or overwritten by a
PDF Magic Opener scan result or a "clean" badge.

`verifyBrowserNativeMalwareWarning(downloadsApi, permissionsApi, completion)`
is a **passive veto** for a future independently authenticated download-to-
native scan integration. It receives only a normalized
`{ kind: "completed", id }` notice, verifies the current optional
`downloads` permission while observing revocations, and queries precisely
`downloads.search({ id })` for a fresh completed, existing download item.
Only the browser's explicitly un-warned `danger: "safe"` or
`danger: "deepScannedSafe"` classifications pass this narrow boundary.
Unknown/missing danger fields, `"accepted"` (a user bypassed an earlier
warning), `"allowlistedByPolicy"`, dangerous/suspicious/pending statuses,
incomplete or deleted downloads, rejected API calls and permission revocations
fail closed. Browser families that cannot supply a trustworthy danger state
need separate, reviewed integration rather than a guessed "safe" default.

Successful lookup returns only a frozen, path-free
`{ id, browserDanger, authorizesScan: false, authorizesOpen: false }` record.
It does not establish malware safety, ClamAV success, file identity,
signature freshness, quarantine clearance or permission to open the PDF.

The existing `submitCompletedPdfDownloadToNative` now requires this
additional permission-checked exact-ID lookup after its final file checks,
and rejects **any** browser `onChanged.danger` event for the in-flight ID.
This preserves warning changes even when they race with scanner handoff.
It never invokes `downloads.acceptDanger`, `downloads.open`,
`downloads.removeFile`, `downloads.erase`, browser warning UI APIs, or
native scanner bypass methods. It never requests new permissions, persists
browsing data, activates the intentionally inert extension background,
changes browser settings, or modifies the installed scanner or user choices.

The new regression tests and updated native submission tests run under
the existing required `scanner-tests` WebExtensions `npm test` stage.
