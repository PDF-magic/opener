# Handle browser restarts during optional PDF interception (opener-0793)

**Safety decision: fail closed.** A cold browser restart invalidates every held
PDF response, scan callback and result token from the previous browser session.
No old PDF is reopened, redirected, re-fetched, released, or automatically
rescanned. An interrupted scan, a restored browser tab and an old "clean"
result are **not** proof of a completed native ClamAV scan. The shared
WebExtension remains disabled; the full browser-to-native integration is
**not implemented**.

The passive `createPdfInterceptionBrowserRestartGuard(coordinator)` provides
the restart lifecycle contract. It exposes `reconcileStartup(startup)`,
`issueTicket()`, `isCurrent(ticket)`, `release(ticket)`, `dispose()` and
a read-only status. It never registers browser listeners, requests permissions,
reads a URL, persists scan state, launches a native host or opens a PDF.

## Cold startup reconciliation

A future *trusted* integration must deliver a real `runtime.onStartup`
cold-start event with an exact, four-field, version-1
`{ version, kind: "browser-startup", browserId, startupId }` record. The
opaque `startupId` is **not** a credential. A browser-specific, synchronous
`verifyColdBrowserStartup` callback must independently verify the event's
origin, installed browser/profile and freshness; a JavaScript Boolean or
page-supplied event is not authentication. In particular, an MV3 **service
worker** wake, navigation, download notification, ordinary extension update,
and a restored tab do **not** count as a new authenticated cold start.

For every accepted fresh startup, the guard:

1. Invalidates every old in-memory ticket synchronously, before invoking any
   user-supplied coordinator callback. Late results cannot be revived by a
   successful network or scanner response.
2. Calls `revokeHeldPdfInterceptions` synchronously, requiring `true`.
   The separately implemented coordinator must abort or disconnect old held
   response filters, cancel local scan callbacks, and prevent any original PDF
   response being unblocked in an unverified state.
3. Calls `cancelOrphanedPdfInterceptions` with **only** the trusted browser
   and startup identifiers, requiring a matching asynchronous confirmation.
   The *native* coordinator must use its own durable, authenticated,
   browser/profile-scoped interception ledger to cancel/reap or quarantine all
   orphaned native scans and private temporary PDF spools, **including those
   unknown to the newly started extension process**. Existing explicit
   user-initiated downloads and other applications' scans are out of scope.
4. Only after both steps succeed permits fresh *lifetime tickets*. Tickets
   never confer scanning, clean-verdict or PDF-open authorization.

If the browser restarts while native cleanup is pending, a newer startup
supersedes the previous generation. Late success from an older startup cannot
re-enable it. Failed verification, missing native coordination, bad or stale
acknowledgements, permission loss, native disconnect, cancellation error,
replayed startup, malformed metadata or disposal all **fail closed**. No
recovery silently resumes or grants a previously held PDF. Old generation
tickets do not survive browser crashes or a new process instance.

## Implementation boundary and dependencies

The installed extension's `background.js` is intentionally inert, and
the current transport-only host cannot authenticate or cancel arbitrary
scanner jobs from a page. Therefore this task introduces the isolated,
testable restart policy **only**; it does not claim a real browser restart
can currently enforce complete pre-render blocking or cancel native jobs.
Before enabling automatic interception, implement a separately audited
authenticated browser startup listener and native orphan ledger/reaper,
effective revocable browser permissions, Firefox response-stream lifecycle
handling, and an end-to-end scanner interlock. A missing or incomplete
reaper is a blocker, not permission to reopen a PDF. Browser session restore
can independently reload a network PDF, so real-browser tests must verify
browser-restored tabs and bypass paths do not escape the hold policy.

The ongoing multiple-tab task (opener-0792) owns per-tab tracking, and
tab closure (opener-0791) owns tab-removal cancellations. This module handles
only **cross-startup epoch invalidation and native orphan reconciliation**,
without duplicating their registries or modifying their PRs.

The existing user preferences, chosen PDF application, ClamAV policy,
browser-native dangerous-download checks and manifest permissions remain
unchanged. `tests/pdf-interception-browser-restart.test.mjs` is included by
the mandatory WebExtensions `npm test` GitHub CI job. Its regression cases
cover cold-start identity, stale results, concurrent starts, orphan cleanup,
failures, replay, browser IDs, ticket bounds, privacy and unchanged safety.
