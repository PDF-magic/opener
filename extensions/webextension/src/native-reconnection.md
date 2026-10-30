# Native connection recovery (opener-0635)

`native-reconnection.js` exports a **dormant**, session-local connection
controller for the future, separately reviewed WebExtensions-to-native host
adapter. No background script imports it; current extension builds **do not**
declare `nativeMessaging`, register a host, start a native connection, or
process PDF files. The application scanner and the user's PDF application
selection are unchanged.

## Connection lifecycle

A trusted integration must first independently establish all of these facts:

1. The locally installed native host `org.pdfmagic.opener` is registered and
   its browser extension identity is approved. The adapter must snapshot the
   **exact, explicitly approved IDs** from the independently verified host
   registration manifest (Chrome/Chromium `allowed_origins` converted to
   canonical extension IDs, or Firefox `allowed_extensions`). A host-name
   match, a browser-supplied request payload, or a boolean from untrusted
   content is **not** registration or authentication.
2. The browser actually granted the required optional native messaging
   permission through the separately reviewed user-initiated permission flow.
3. The user explicitly approved this connection session.

Only that trusted integration may inject a **bound**
`browser.runtime.connectNative`-compatible function, the browser-provided
`runtime.id` (copied into a plain `{ id }` record), a reviewed `browserKind`
(`chromium` or `firefox`), and `approvedExtensionIds` from the verified
local registration. It then invokes `controller.start({
 registrationVerified: true, nativePermissionGranted: true,
 userApproved: true })`. The controller **fails closed before opening any
native port** if the identity is missing or not in that exact allowlist, if
the list is empty, malformed or wildcard-based, or if a Firefox development
ID is used without explicit `development: true`. It snapshots the approved
list and rechecks the current runtime ID before each reconnect. IDs are
case-sensitive and must match browser-specific formats. No identity is
approved by default.
The module does not itself discover or authenticate the browser process or
registration: the trusted integration must do so using browser-controlled
metadata and a securely verified host manifest. Command-line origin flags
and caller-provided records can be spoofed by another local process; exact
ID matching is an **additional admission control, not process authentication**.
The module does not request permissions.
The currently inactive manifest has no native messaging permission, so it
must not invoke `start()` in production.

A new port sends **only** the existing v1 `host.handshake` request with a fresh
Web Crypto challenge and correlated request ID. The controller accepts the
exact transport-only handshake reply from `Host.swift`, requiring the echoed
challenge, compatible version, `scanAvailable: false`, and the documented
read-only host metadata. It must not treat a ping, an unsolicited reply, a
cached response, or scanner claims as readiness or authentication.

A valid handshake enters `ready` (**transport-ready only**). A lost port,
failed connection attempt or a missing handshake reply after five seconds
invalidates that port, discards its handshake state, and attempts a new
native host process with a new challenge. Retries use delays of 250, 500 and
1000 milliseconds, with at most **three** retries per explicitly approved
session (including disconnects after successful handshakes). After that the
controller reports `unavailable` and stops. It never loops indefinitely.
Malformed or privileged handshake responses instead enter `protocol-error`
and **do not retry**. Calling `stop()` closes the port, cancels pending retry
and handshake timers, and invalidates late callbacks. A new `start()` needs
fresh affirmative authorization; no approval is persisted across extension
worker termination, browser restart or controller restart.

No request or job is queued or replayed. In particular, the controller
**never sends** `scan.request`, `scan.status`, `scan.result`, `scan.cancel`,
file paths, download metadata, scanner verdicts, or PDF-open instructions.
A future authenticated coordinator and request API require separate security
review, explicit trusted file selection, ClamAV signature freshness, complete
scanning, integrity, quarantine, and verified application handoff. Reconnect
must never turn an unavailable/failed scan into a clean result or authorize
PDF opening. Port failures are reported as coarse state strings without
exposing host paths, browser errors or document contents.

## Tests and CI

`node --test tests/native-reconnection.test.mjs` covers approval gating,
handshake correlation, reconnect/reset, capped retry timing, timeouts,
malformed and privileged responses, stale callbacks, cancellation/cleanup,
and the inactive background boundary. `npm test` includes these tests through
its existing `tests/*.test.mjs` glob. The `scanner-tests` GitHub Actions job
runs `npm test` after the WebExtension build/package tests. The existing
macOS compiled-host tests separately verify handshake state is per process.
