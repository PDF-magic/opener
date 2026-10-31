# Avoid extension ↔ PDFOpener navigation loops (opener-0786)

A future automatic PDF interception path must never automatically intercept its
own extension viewer, a PDFOpener-originated reopening, or a destination that
returns to either application. Repeated browser events, redirect chains and
failed or timed-out handoffs must not create a browser → extension → PDFOpener →
browser loop. This guard is **passive** until a separately reviewed integration
is connected; the installed `background.js` remains inert.

The reusable [loop guard](pdf-interception-navigation-loop-guard.js) exposes
`createPdfInterceptionNavigationLoopGuard(coordinator).reserveAttempt(reference)`.
A reference contains an opaque request ID and a valid top-level tab/frame ID.
Only a separately authenticated coordinator can provide a synchronous
`readVerifiedNavigation` result confirming the same request/tab/frame,
an opaque navigation ID, and a browser-verified origin/destination. That
result must derive from trusted browser and native session state, never page
scripts, untrusted redirect parameters, referrer strings, query markers or
self-asserted flags. The marker `verified: true` **cannot itself prove** this
provenance.

| Provenance and destination | Decision |
| --- | --- |
| Verified external web navigation → web PDF candidate, first attempt in tab | Reserve one attempt for further independent validation |
| Extension-owned viewer or extension-bound redirect | Suppress automatic interception |
| PDFOpener-initiated opening or PDFOpener-bound redirect | Suppress automatic interception |
| Duplicate request, repeated tab, changed navigation ID or redirect cycle | Suppress automatic interception |
| Unknown, malformed, unverified, subframe, capacity exhausted, disposed | Fail closed; suppress automatic interception |

The guard reserves **before** any subsequent asynchronous scanner handoff.
No callback can cancel or release a reservation due to a rejection, timeout,
navigation, or retry. Reuse the same session-owned guard across browser event
paths; 256 lifetime reservations is a bounded fail-closed limit, not a rolling
cache. Only disposal ends its lifetime. A future real interception coordinator
must additionally persist loop suppression across service worker restarts,
correlate PDFOpener-originated launches even across new tabs, and validate
actual browser provenance and tab closure; this in-memory module cannot do
those things by itself. It must **never** fall back to a different automatic
redirect when verification is missing. A page's URL alone cannot prove who
launched it.

A successful `reserved-for-independent-review` outcome is not permission
to redirect or scan. Every outcome sets `navigationRequested: false`,
`scanVerified: false`, `authorizesScan: false` and `authorizesOpen: false`.
No complete file, ClamAV verdict, quarantine result or selected PDF
application is vouched for. The existing
[pdf-preload-interception-trigger.js](pdf-preload-interception-trigger.js)
still disallows using late or nonblocking navigation events as a pre-render
gate. A future activation must separately verify opt-in site permissions,
effective request blocking, native PDF bytes, scanner safety and user
preferences. The browser extension does not yet implement interception.

There are no navigation listeners, tab updates, redirects, downloads, storage,
native messaging, scanner calls, manifest privileges or preference changes
in this task. Regression cases in
`tests/pdf-interception-navigation-loop-guard.test.mjs` run through the
existing WebExtensions `npm test` and GitHub `scanner-tests` CI.
