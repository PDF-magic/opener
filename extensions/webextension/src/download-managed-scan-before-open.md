# Require completed native scanning before managed opening (opener-0719)

`createManagedScanBeforeOpenGate(coordinator)` provides a **passive,
session-owned safety boundary** for the opt-in managed download workflow
added in opener-0718. Its method
`await gate.requestOpenIfScanned(managedRequestId)` can **send a native
open request only after** a correlated, completed, verified **clean**
native scan report is returned. No user-visible browser opening or scanner
service is activated by this file.

The injected `coordinator` is a **separately authenticated native
component**, not page-provided data. It must implement all of:

- `nativeManagedWorkflowReady === true`,
  `nativeScanResultsReady === true`, and
  `nativeVerifiedOpeningReady === true`. These flags are advisory
  prerequisites, **not credentials** or evidence that a scan succeeded.
- `readVerifiedManagedScanResult(managedRequestId)` returning a Promise
  for an **independently trusted native** result. It must derive the
  verdict from actual complete ClamAV scanning with current signatures,
  the applicable built-in protection policy, immutable recorded scan
  context, file identity and bytes, and current native session state.
- `requestVerifiedManagedOpen({managedRequestId})` returning a Promise.
  This **native-only** operation MUST independently recheck all required
  scanner, signature, canonical file identity, current bytes, quarantine,
  user intent and selected application gates immediately before launch.
  It must not trust the JavaScript scan result as permission to open.

The only accepted native scan report has exactly these fields:

```json
{
  "schemaVersion": 1,
  "managedRequestId": "managed_7",
  "status": "complete",
  "scanCompleted": true,
  "scanVerified": true,
  "authorizesOpen": false,
  "result": { "status": "clean" }
}
```

The strict shape is a **validation contract, not authentication**.
`authorizesOpen: false` means even a clean informational scan record
cannot itself approve opening. The gate must run within an already
authenticated native session and the final native open handler must
revalidate everything independently. Pending, unavailable, incomplete,
cancelled, timed-out, interrupted, failed, malicious, suspicious, missing,
changed-file, mismatched, accessor-backed or otherwise ambiguous results
**never** call `requestVerifiedManagedOpen`. A response from the
current transport-only host, a browser `danger: "safe"` label, or a
managed request queue acknowledgment is not scanner evidence.

The gate reserves its opaque ASCII `managedRequestId` **synchronously**
before the asynchronous scan-result check, preventing concurrent duplicate
open commands. Every attempt consumes that ID even when verification
fails or a callback is rejected; a new native session and separate
verified job identity are required before a legitimate new attempt.
`dispose()` prevents future calls and invalidates pending replies.
Uncertain native requests are not automatically retried or cancelled.
The trusted native coordinator must additionally enforce idempotence and
reconciliation after reconnection or a restart.

The only native-open argument is the frozen, exact one-field
`{managedRequestId}` object. No URL, downloaded path, cookies,
browser metadata, scanner report, file bytes or application preference
crosses this interface. An opening acknowledgment must be exactly
`{accepted: true, managedRequestId: <same ID>}`, but even then the
gate returns only the frozen `request-submitted` state with
`scanVerified: false`, `authorizesOpen: false`, `opened: false`.
It never claims that the scanner or opener succeeded or shows private
native errors.

**Production prerequisite:** The repository's installed native messaging
host is currently **transport-only** and cannot yet provide the
authenticated coordinator methods described above. The WebExtension
background and popup remain inactive; this gate is therefore an
implementation-ready internal contract, **not a working production
browser-to-native scanner or opening service**. Future integration
must hook the gate into a single trusted coordinator session and preserve
all native scan safeguards. This PR neither activates browser downloads
nor extends permissions, changes preferences or touches `scan-and-open.py`.

The 15 regressions in
`tests/download-managed-scan-before-open.test.mjs` run with the existing
WebExtensions `npm test` under `scanner-tests`. They require successful
completed verified native scans for opening and reject every nonclean,
untrusted or miscorrelated outcome, including asynchronous readiness
revocation and stale replies. See
`download-managed-open.md` for the preceding user-consent and native
request-submission stage.
