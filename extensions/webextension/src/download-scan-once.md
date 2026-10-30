# Prevent duplicate scan requests for a completed download (opener-0691)

`createCompletedDownloadScanRequestGate(downloadsApi)` returns a passive,
opt-in `{ submitOnce, dispose }` gate for a future trusted download-to-scan
integration. The extension's background script remains inactive. Importing
the gate has **no** browser or native side effects; a trusted, consent- and
permission-checked coordinator must explicitly construct it.

`submitOnce(preflight, submitScanRequest)` accepts only the frozen-shape
`{ id, transferComplete: true, scanVerified: false, authorizesScan: false,
authorizesOpen: false }` result from the previously reviewed
`preflightCompletedDownloadForScan` contract. The gate itself does **not**
authenticate that contract, verify file stability, enable permissions, or
create a native scanner connection. The trusted caller is responsible for
those prerequisites and for canonical file identity validation.

The gate reserves a numeric browser download ID **synchronously before**
calling or awaiting the supplied request callback. Subsequent submissions
for that ID are rejected as `duplicate` even if the callback is still
pending, throws, rejects, returns a negative acknowledgment, or finishes.
Successful acknowledgment means only `request-submitted` and never a
clean scan or permission to open. The callback receives **no arguments**,
preventing this layer from forwarding browser paths, URLs, credentials or
files to a native host.

Up to 256 distinct IDs are tracked in memory. **Reservations are not evicted**
when this limit is reached; additional IDs fail closed as
`capacity-exhausted`, rather than accidentally permitting a duplicate scan
for an older download. The underlying passive browser download-event
adapter observes `onCreated` and `onErased` events to release a reservation
when an ID is genuinely reusable. `dispose()` removes listeners, clears
memory and rejects future calls. Process restarts do not preserve reservations;
a future enabled native scan coordinator must also enforce durable idempotency
across independent extension sessions and processes. This task introduces no
such integration or persistent browser data.

This guard does not supersede ClamAV signature freshness, complete-file
scanning, integrity, quarantine, native request validation, or the user's
selected PDF application. It never automatically scans or opens a download.

Eleven focused regression tests are discovered by the existing
WebExtensions `npm test` stage in required `scanner-tests` CI.
