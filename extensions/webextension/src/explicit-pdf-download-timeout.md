# Explicit PDF download timeout (opener-0771)

The opt-in \`createExplicitPdfDownloadTimeout\` watchdog enforces a wall-clock
deadline for an **already started, authenticated Scan This PDF** browser
download. Default timeout: **120 seconds**. A separately configured timeout
may be shorter or up to a hard **300-second** maximum; zero, negative,
fractional and greater values are rejected. It never changes user preferences
or the browser's download destination.

## Enforcement

\`watch(explicitScanRequest, downloadId, timeoutMs?)\` requires the existing
seven-field explicit scan request and a nonnegative browser download ID. An
authenticated, trusted coordinator must explicitly set
\`downloadTimeoutReady: true\` and implement a synchronous, own,
network-free \`readVerifiedActiveDownload(reference)\` method. Its result must
contain **exactly** \`requestId\`, \`downloadId\`, \`selectionId\`, \`tabId\`,
\`frameId\`, \`startedAtMs\`, \`state\`, \`verified: true\` and
\`permissionGranted: true\`. The coordinator must independently establish
the association between current user selection and download, obtain the
start timestamp from trusted browser/transport evidence, confirm origin and
permissions, and disallow reusing IDs for a different document.

The watchdog computes the deadline from that original \`startedAtMs\`, not
from the time that monitoring attaches. It subscribes to the existing,
allowlisted \`downloads.onChanged\` feed, checks the browser download ID
exactly, and independently re-reads trusted download state before treating a
\`complete\` event as transfer completion. \`interrupted\`, \`erased\`,
mismatched IDs, stale selection, revoked access and invalid evidence fail
closed. A browser completion received **at or after** the deadline never
changes an expired transfer into a success.

When the deadline is reached and the same download is still authenticated and
in progress, the attempt is **blocked synchronously before** requesting
\`downloads.cancel(downloadId)\`. Cancellation is best-effort: even a
rejected or throwing browser API cannot turn the expired result into success.
No cancellation of a different or unverified download is permitted.
\`session.dispose()\` and \`manager.dispose()\` stop monitoring and request
cancellation only for a still-verified active download. Sessions detach all
listeners and clear timers on every terminal outcome. Request IDs cannot be
replayed or concurrently monitored; caches and active watches are bounded.

The returned immutable \`session.state()\` and \`session.done\` contain no
URL, filename, path, credentials, PDF bytes or scanner result. A status of
\`completed\` means **browser transfer complete only**. The manager's
\`isBlocked(requestId)\` returns true unless that request has a trusted
completion, but a false result never grants scan/open permission. Native
ClamAV signatures, file integrity, quarantine, protected browser downloads
and mandatory scan-before-open remain independent requirements.

## Integration prerequisites

The shipped WebExtension is deliberately inactive: its background registers
no listeners, and the manifest has no host permissions. This task provides a
**real, opt-in timer and browser cancel mechanism** for a trusted adapter to
invoke; it does not activate background downloads. The adapter must call
\`watch\` as soon as a verified download ID exists and enforce the block on
every native handoff. Acquisition **before** an ID exists must separately
enforce its own bounded wait or cancellation; this watchdog cannot cancel a
download whose ID the browser has not yet returned.

Browser extension service workers may be suspended, during which JavaScript
timers are not guaranteed to fire. A future production adapter must persist
non-secret request/deadline state in a trusted, bounded lifetime coordinator
and recheck deadlines on worker resume (and on subsequent completion events).
\`session.checkDeadline()\` supplies an explicit recheck while the watchdog
instance remains active. The coordinator must never treat a suspended or
untracked transfer as scanned/authorized.

The deterministic \`tests/explicit-pdf-download-timeout.test.mjs\` covers
exact deadline enforcement, late completions, early wakeups, cancellation
errors, forged events, stale identities and permission loss, cleanup,
timeout policy bounds, no-op imports and unchanged scanner/browser safety.
The existing WebExtensions \`npm test\` wildcard and \`scanner-tests\` GitHub CI
automatically run all 17 regression groups.
