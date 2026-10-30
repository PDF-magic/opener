# Safely abandon interrupted download scan requests (opener-0709)

\`createPendingDownloadScanRecovery(downloadsApi, nativePort)\` is a
**passive, explicitly instantiated** helper for a future authenticated
browser-to-native download scanner coordinator. Its recovery policy is
**safe abandonment**, not automatic replay. A native scanner request may
already be running or have completed when its browser Port disconnects;
re-submitting without native reconciliation can duplicate scans or
trigger a second opening. The currently installed standalone native
host remains **transport-only** and returns
\`trusted-scan-coordinator-required\`. This module cannot start,
resume, or authorize native scans by itself.

## Trusted registration

A separately authenticated native coordinator, with independently
verified extension origin, permissions and user consent, must supply its
active native Port and the complete browser \`downloads\` event source.
It may call \`track(submission, scanRequestId, cancelPendingScan)\`
**only after the native coordinator accepts** a completed-PDF scan
request and the existing session-owned scan-once gate has reserved it.
The submission must be an exact object with:
\`{status:"submitted",id,scanSubmitted:true,scanVerified:false,
authorizesOpen:false}\`. The correlated native request ID is a bounded
opaque ASCII string. This helper retains no file path, URL, scanner
diagnostics, PDF bytes, browser credentials, or application preference.
It does not assume the boolean properties themselves authenticate a
native host: origin, protocol and scanner verification are performed by
the trusted coordinator.

Every successful registration returns an opaque Symbol token.
\`state(token)\` returns a fixed \`pending\` state only while both the
download and native Port remain valid; no state ever verifies a scan
or authorizes opening. Only one pending request per exact download ID
and native scan request ID is admitted. The 256-entry cap fails closed,
without evicting an older request.

## Interruption and abandoned-request behavior

The helper composes the existing verified
\`subscribeToDownloadEvents\` and
\`createNativeScanDisconnectGuard\`:
- **Download interruption, error, file rename, changed danger,
  non-complete state, erasure or ID reuse:** revoke the matching token
  and invoke its native cancellation callback; unrelated downloads
  continue. A completed status change with no other mutations
  is not a reason to cancel.
- **Native Port disconnect or explicit \`dispose()\`:** revoke all
  pending tokens *before* invoking cancellation callbacks. Cleanup
  errors/rejections are contained so other requests are still
  abandoned. Late results cannot become valid again.
- **Unknown outcome:** no automatic resubmission or restoration of
  a purported clean result. Abandoned IDs remain blocked in this
  session until an independently observed new \`onCreated\` lifecycle.
  A new native Port requires a **new authenticated coordinator and
  guard**, not reuse of old tokens. On restart, there is no durable
  queue to replay.
- **Normal native lifecycle completion:** trusted callers may
  \`release(token)\` to stop tracking a finished operation, but
  release returns only an ownership boolean: **not** scanner clearance,
  opening permission, or permission for a duplicate scan. The native
  coordinator still has to validate the scan verdict, file identity,
  signature freshness, quarantine and selected PDF application
  independently at handoff.

The callback \`cancelPendingScan\` must cancel/reap only the
coordinator-owned native scan, or safely mark an unknown outcome as
abandoned in the trusted native process. This helper **cannot prove
that cancellation succeeded** or undo an already completed native
operation. In particular, a detached UI or browser worker must never
interpret a failed cancellation as permission to retry. Any future
resumption requires a **separately reviewed, authenticated native
reconciliation protocol**, an exact scan-job identity check, refreshed
download permissions and identity, and the established no-duplicate
scan gate. It is deliberately out of this task's scope.

## Tests and safety

The 15 regressions in
\`extensions/webextension/tests/download-pending-recovery.test.mjs\`
run automatically under the existing WebExtensions \`npm test\` in
GitHub's \`scanner-tests\` job. They cover independent pending IDs,
interruptions, erasure/ID reuse, filename and danger changes, Port
disconnection, cleanup failure, reentrant callbacks, duplicate
registrations, strict input validation, capacity, release, shutdown,
subscription rollback and inert background behavior.

The installed extension's background stays inactive. No native message,
browser permission request, scanner invocation, preference write,
browser file opening or new user-facing approval is introduced. Existing
ClamAV, file-integrity, quarantine, mandatory failure and application
selection protections remain authoritative.
