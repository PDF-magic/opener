# Report native scan progress to the extension (opener-0694)

`relayTrustedScanProgress(coordinator, scanRequestId, deliverToExtension)`
is a **passive** adapter for a **separately authenticated, trusted** native
scanner coordinator. Nothing connects, scans, subscribes, or sends messages
when the module is imported. The actual current standalone native host has
no scanner coordination and continues to answer `scan.status` as
`unavailable` with `trusted-scan-coordinator-required`; no progress can
be truthfully reported from that host today.

A future reviewed integration must independently verify a native session
and an **accepted scan associated with the request ID**, then inject a
coordinator exposing own data properties `nativeScannerReady: true` and
`subscribeScanProgress(scanRequestId, listener)`. The latter must only emit
**actual scan lifecycle observations** and immediately return a synchronous
unsubscriber. `nativeScannerReady` is an availability flag, **not**
authentication or authorization; neither browser metadata nor an untrusted
message may create the coordinator. The integration must deliver the
resulting event to an already authenticated extension message receiver,
after separately validating the extension's sender.

For a matching, bounded `scanRequestId`, the module accepts only records
with exactly `scanRequestId`, `stage`, and optional `percent` fields.
Supported stages are `queued`, `starting`, `scanning`, and `verifying`.
Percentages are **optional** measured integers from 0 to 99. If the native
scanner cannot measure a truthful percentage, **omit** it. Regressing stage
or measured percentage values are ignored. Results, completion, clean
verdicts, file paths, diagnostic strings and extra fields are rejected.

Each accepted observation is delivered through the supplied callback as
a validated, detached and frozen version-1 extension event:

```json
{"version":1,"kind":"event","topic":"scan.progress","requestId":"scan_123","payload":{"scanRequestId":"scan_123","stage":"scanning","percent":30}}
```

The event is bounded by the shared 16 KiB message limit and does **not**
mean that the scan passed, finished, or authorized opening. A terminal
result must be independently verified by the trusted scanner coordinator,
and existing ClamAV signature freshness, malware scanning, integrity,
quarantine, user-selected app and safe opening gates remain mandatory.
The adapter installs no browser listeners, opens no native port, never
requests permissions or reads PDF bytes, and does not modify preferences.
Call the returned idempotent unsubscriber at end-of-scan, on disconnect,
or when extension delivery ends; a lost native-ready flag also stops
reporting. Errors are sanitized and not forwarded to the extension.

The focused tests `node --test tests/scan-progress-relay.test.mjs` are
included in existing `npm test` and the required `scanner-tests` CI.
Production activation remains dependent on the independent native
coordinator and accepted scan lifecycle; the open download submission
PR #458 is related but does not provide that coordinator by itself.
