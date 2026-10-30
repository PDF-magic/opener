# Completed PDF download submission boundary (opener-0692)

`submitCompletedPdfDownloadToNative({ downloadsApi, permissionsApi,
completion, coordinator, scanGate })` is an **explicitly invoked, one-shot** adapter
between the existing completed-download detection helpers and an
**independently authenticated native scanner coordinator**. It does not
install a browser event listener or initiate a native transport on import.
The current WebExtension background remains inactive, and the standalone
native host still rejects `scan.request` with
`trusted-scan-coordinator-required`. Production submission is unavailable
**until a separate trusted native coordinator is installed and verified**;
the readiness flag alone does not authenticate the host.

A future trusted integration must obtain user consent and establish the
native session independently, provide a persistent session-owned
`createCompletedDownloadScanRequestGate(downloadsApi)` from merged task
opener-0691, and inject a coordinator exposing the own
`nativeScannerReady: true` data property and
`submitCompletedPdfDownload(request)` async method. The latter must
perform its own canonical identity, local file stability, permission and
ClamAV policy checks; its `{ accepted: true }` result means **submission
accepted**, not malware clearance or permission to open the file. The
adapter intentionally never constructs native messaging payloads or uses
the presently path-free `scan.request` protocol to bypass host admission.

The adapter accepts only a valid `{ kind: "completed", id }` record,
uses the existing exact-ID, revocation-aware download scan preflight
(which requires `state: "complete"`, `exists: true`, consistent transfer
bytes, and no partial filename), obtains the already permission-checked
local path and MIME, and classifies the result as a PDF *candidate* by
declared PDF MIME or a `.pdf` filename when MIME is unknown/generic.
An explicit non-PDF MIME declaration vetoes the suffix hint. It then
repeats the browser preflight and absolute path lookup, rejecting any
changed path. A scoped download event observer invalidates ID reuse,
erasure, errors, or rename events, while a separate permission-revocation
observer spans the complete asynchronous operation. A request is offered
only when those checks succeed and the injected native coordinator still
reports readiness. The request contains only
`Object.freeze({ id, localPath })`. Before invoking the injected coordinator, the existing session-owned scan
gate atomically reserves that completed download ID. Duplicate notifications
cannot issue duplicate native requests, even when callbacks are pending.
The ID can be reused only after the existing gate observes a new/erased
browser lifecycle event. Any exception, failure, stale state,
revocation, or non-Promise callback response fails closed.

A successful acceptance returns a detached frozen
`{ status: "submitted", id, scanSubmitted: true, scanVerified: false,
authorizesOpen: false }`. All refusals return a fixed path-free
`{ status: "unavailable", scanSubmitted: false, scanVerified: false,
authorizesOpen: false }`. Browser IDs and paths are untrusted: the
native side must still verify canonical file identity, symlink and
regular-file constraints, file stability, ClamAV signature freshness,
complete scanning, integrity, quarantine and the user-selected PDF
application. A browser check cannot replace native checks or guarantee
no file has changed since the lookup.

This task **does not enable automatic scanning** in the installed
WebExtension; it changes no host protocol, scanner, scanner safety gate,
browser manifest, permission request, user preferences, or background
worker. The separately reviewed authenticated transport and native
scanner coordinator are prerequisites to production activation.

The 15 regression tests in
`extensions/webextension/tests/download-native-submit.test.mjs` run as
part of existing `npm test` in GitHub's `scanner-tests` job. They exercise
correct and misleading PDF filename signals, exact-ID lookups, early
exits, missing files, incomplete transfers, permission denial and
revocation, stale browser events, changed paths, rejected submissions,
error privacy, ID-based duplicate submission suppression, and inactive startup behavior.
