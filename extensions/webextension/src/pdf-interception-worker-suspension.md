# Handle service-worker suspension during automatic PDF interception (opener-0795)

**Safety decision: fail closed.** A Manifest V3 background service worker
may be suspended or terminated between callbacks, **without** a usable
`runtime.onSuspend` notification and without time for asynchronous cleanup.
A suspended worker's JavaScript timers, promises, response callbacks and
in-memory tokens cannot be used as durable scanner evidence. The shipped
WebExtension remains inactive and this is **not implemented** as a live PDF
interception flow.

The passive `createPdfInterceptionWorkerSuspensionGuard(coordinator)` exports
`reconcileWake(wake)`, `suspend()`, `issueTicket()`,
`isCurrent(ticket)`, `release(ticket)`, `dispose()` and read-only
`status`. No browser listeners are registered on import or by construction,
and no native messaging, permissions, network access, stored browser state,
PDF release, open command or user preferences are changed.

## Trusted worker activation and fail-closed reconciliation

Every *new real worker activation*, including a wake after silent suspension
**in the same browser session**, needs a unique, independently attested
`{version:1, kind:"service-worker-activation", browserId, activationId}`.
This is not a credential and must not be accepted from a page, a restored tab,
an arbitrary message, or a previously persisted worker state. The
`verifyWorkerActivation` callback must establish browser/profile origin and
freshness synchronously and independently of this object.

Before another worker lifetime ticket can be issued:

1. The guard immediately invalidates all previous in-memory tickets (before
   calling privileged revocation or scan cleanup functions).
2. `revokePreviousWorkerHolds` must synchronously confirm it has invalidated
   the previous worker's browser response callbacks and holds. An async
   response or failure is not acceptable.
3. `cancelOrphanedWorkerScans` must produce a matching **asynchronous
   native orphan cleanup acknowledgement**, even when the new worker knows
   no prior scan IDs. A native durable ledger should cancel/reap private
   scan jobs, clean/quarantine abandoned temporary PDFs and ensure expired
   response holds cannot release original PDF bytes.
4. Only then may the new worker create bounded *local lifetime tickets*.
   Those tickets do **not** prove a scan was started, completed or clean and
   never authorize PDF opening, releasing bytes or requesting native scans.

Calling `suspend()` is synchronous and invalidates all local tickets
**before** best-effort revocation and cancellation. The method never awaits
asynchronous cleanup, since `runtime.onSuspend` is not guaranteed and
browser APIs may cease running before promises settle. Multiple suspend
events are idempotent; callback failure, disconnection and stale
acknowledgements never restore a token. On a subsequent activation, native
orphan reconciliation is required again. An abrupt kill without notification
is addressed by the **native-held, bounded durable lease**, not a service
worker timer. An expired lease must fail closed independently, even when
the extension never wakes again. The browser's own PDF viewer and external
file-opening paths are **not** controlled by this passive guard.

The code rejects replayed activation IDs, wrong-browser acknowledgements,
forged clean or open flags, accessors/proxies, missing callbacks,
asynchronous proof/revocation, old worker completions, concurrent wakes,
re-entrant verification, suspension during verification, or disposal.
Every returned outcome says `scanVerified:false`,
`automaticInterceptionEnabled:false`, `authorizesScan:false`, and
`authorizesOpen:false`. No URLs, filenames, private paths, native error
messages or browser tokens appear in results.

## Dependencies and related scopes

- **Existing** browser session closure cancellation (#470) observes worker
  suspend and native disconnect, but a listener alone cannot reliably catch
  silent MV3 termination.
- **Separate** browser restart reconciliation (opener-0793, PR #549)
  processes verified cold browser startups, not same-session service-worker
  wakes. This guard neither imports nor duplicates that PR's implementation.
- **Prerequisite for live enforcement:** independently authenticated native
  browser-to-scanner coordination, durable per-browser worker leases and
  orphan cleanup, actual pre-render response filtering/holding support,
  scanner integrity and ClamAV freshness verification, and real browser
  suspension/termination testing. Those are not present yet. If this
  prerequisite fails, do not open or auto-rescan the interrupted PDF.

The static fail page, native scanner quarantine, user-selected applications,
host permissions and browser warnings stay untouched. The focused
`tests/pdf-interception-worker-suspension.test.mjs` suite is exercised by
the dedicated `scanner-tests` CI step and the existing WebExtensions
`npm test` wildcard.
