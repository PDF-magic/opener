# Fail closed across extension restarts (opener-0794)

**Status:** dormant future-coordinator contract. The shared WebExtension still has
an inert background and no automatic interception permission. Neither the
browser nor the native host currently exposes an authenticated live interception
hold and orphan-reconciliation path. Do not enable or attach this helper to
background.js until those separately reviewed prerequisites are satisfied.

createPdfInterceptionExtensionRestartGuard(coordinator) covers fresh
**extension execution contexts**, rather than the separate cold **browser**
restarts addressed by opener-0793. The trigger must be established by a trusted
coordinator on each new MV3 worker process/extension context, reload or update.
runtime.onStartup is not a comprehensive service-worker restart detector;
runtime.onSuspend is not guaranteed to run on a crash. A new worker MUST NOT
reconstitute previously claimed clean scan results from storage or tabs.

On a valid versioned context event with opaque epoch ID and one of
worker-reinitialized, extension-reloaded or extension-updated, the guard:

1. Revokes all previously issued in-memory lifetime tickets synchronously.
2. Calls verifyExtensionContextEpoch({epochId, reason}) for independently
   authenticated, synchronous proof of this exact context. Page messages,
   extension storage, or a caller's self-declared flag are NOT proof.
3. Calls quarantinePreviousExtensionHolds({epochId, reason}), which must
   synchronously make *all* previous holding pages and response releases
   non-resumable without navigating, fetching a URL or replaying PDF bytes.
4. Requires an exact, asynchronously correlated result from
   cancelOrphanedExtensionScans({epochId, reason}). The trusted native
   coordinator must consult a durable ledger of accepted native scan jobs,
   cancel/reap or quarantine orphaned jobs, and prevent old completion results
   from opening PDFs or rejoining the new extension context.
5. Only after both barriers succeed may it issue memory-only tickets for
   **new**, independently authenticated scan lifetimes. These tickets do not
   verify scanning, permit interception or authorize opening.

An unknown outcome, native disconnection, missing grants, stale epoch,
concurrent restart, late native reply, missing hook, changed coordinator,
callback error or unsupported context **remains blocked**. No automatic retry,
resubmission, restoration of old tab state, persistent clean verdict or
browser opening is performed. Cleanup acknowledgement is NOT proof that a
browser or OS has prevented all independent PDF opening paths.

This component neither changes host permissions nor modifies scanner policy,
ClamAV signatures, native quarantine, preferred browser/PDF application,
browser history or the user's settings. The separately authenticated native
coordinator and opt-in pre-render interception/holding integration are the
precise prerequisites for live behavior. It is deliberately independent of
opener-0793's browser-cold-start handler.

tests/pdf-interception-extension-restart.test.mjs is discovered by the
existing npm test script (run in the scanner-tests CI job). It exercises
start/update/reload, strict origin/epoch correlation, synchronous revocation,
reentrancy, races, stale tokens, cleanup failures and unchanged permissions.
