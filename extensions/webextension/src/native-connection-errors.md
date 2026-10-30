# Native connection error responses (opener-0633)

When a future, separately authorized browser-to-native adapter cannot establish
or maintain a native host connection, it can return a **local** correlated v1
response to its extension caller. The native host cannot send an error over a
channel that was never established or has already disconnected.

`createNativeConnectionErrorResponse(requestId, code)` in
`native-connection-errors.js` uses the existing `messaging.js` envelope:

```json
{"version":1,"kind":"response","topic":"host.connection","requestId":"connection_1","payload":{"status":"error","code":"native-host-unavailable","connected":false,"scanAvailable":false,"scanStarted":false,"scanVerified":false,"authorizesOpen":false}}
```

Trusted connection lifecycle code selects one of the stable, privacy-safe codes:
`native-host-unavailable`, `native-permission-denied`,
`native-connection-disconnected`, `native-handshake-failed`, or
`native-connection-timeout`. Unrecognized codes, browser exceptions and
platform-specific diagnostic strings are reduced to `native-connection-failed`.
The validated request ID is retained for correlation. This deliberately avoids
copying raw browser errors, native host paths, document names or other user data.

The helper **does not** connect or reconnect, register/install a host, request
native messaging permission, listen for browser events, read documents, trigger
scans, or change user settings. The extension remains inactive without a
registered/authenticated native messaging host and a separately reviewed,
user-consented integration. No error response is an authenticated host reply,
scanner result, verified clean verdict or PDF-opening authorization.

Malformed or truncated frames received **by** the standalone native host still
fail closed without a response or diagnostics; this helper is for errors
observed **by the browser-side caller**, not for protocol input rejection.
Future integration must enforce authenticated local host registration, explicit
permission, scanner signature freshness, integrity, quarantine and verified
PDF opening independently of these status values.

Run `node --test tests/native-connection-errors.test.mjs` from
`extensions/webextension/`. The existing `npm test` suite discovers these
regressions in required GitHub CI without granting additional permissions.
