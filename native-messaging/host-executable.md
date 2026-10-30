# Native messaging host executable (opener-0615)

`Host.swift` is a **standalone native executable source** for macOS. Build it with the system Swift compiler:

```sh
xcrun swiftc -O -parse-as-library -warnings-as-errors native-messaging/Host.swift -o /path/to/pdf-magic-native-host
```

The output is a real process executable, not a browser extension or PDF handler. It speaks browser native messaging transport: a 32-bit little-endian byte length followed by UTF-8 JSON on standard input, and the same framing on standard output. Frames are bounded to 16 KiB, matching the shared WebExtensions message envelope.

### Connection handshake (opener-0624)

A new native host process starts **without a completed handshake**. To confirm the
supported protocol and correlate the connection, send one version-1 request:

```json
{"version":1,"kind":"request","topic":"host.handshake","requestId":"hello_1","payload":{"clientNonce":"Client_Challenge_123456789"}}
```

The host acknowledges with the same `requestId` and `clientNonce`.
Its example below reflects an environment without a registered SwiftUI app,
where `applicationVersion` must be `null`, and with the current Built-in
protection policy:


```json
{"version":1,"kind":"response","topic":"host.handshake","requestId":"hello_1","payload":{"status":"transport-only","protocolVersion":1,"clientNonce":"Client_Challenge_123456789","applicationVersion":null,"activeProtectionProfile":"built-in","scanAvailable":false}}
```

### Read-only installed status (opener-0625)

Every successful `host.handshake` response includes three informational fields:

- `applicationVersion`: the installed **PDF Magic Opener SwiftUI application**
  `CFBundleShortVersionString`, obtained from the locally registered application
  matching bundle ID `local.studio.pdfmagicopener.swiftui`. This is **not** the
  host executable version, Safari extension version, or a build-time guess.
  It is `null` if the app cannot be resolved or its metadata fails validation.
- `protocolVersion`: integer `1`, the actual native message protocol
  supported by this host.
- `activeProtectionProfile`: `"built-in"` only when the existing
  `local.studio.pdf-magic-opener` shared preference has no explicit selection
  or contains the sole supported `selectedProtectionProfile: "built-in"`.
  Unknown or planned Standard/Enhanced/Maximum selections, malformed saved
  values, or inaccessible preferences are reported as `null`, **never**
  silently advertised as enforced alternative profiles.

These fields are read-only metadata, not proof that a scan passed, that ClamAV
is healthy, that a host/browser is authenticated, or that opening a PDF is
permitted. The native host does not change user preferences, install or invoke
scanners, register a browser native messaging origin, or read document contents.
The installed scanner continues to enforce its independent fail-closed policy.
Regression coverage includes compiled-host responses and standalone Swift tests
with isolated app-bundle fixtures.

The `clientNonce` must contain **16–64 ASCII letters, digits, underscores, or
hyphens**. The host rejects a malformed nonce, unknown fields, incompatible
version, or **second handshake on the same process**, without an error response
or diagnostics. Reconnecting creates a new process with fresh handshake state.
The confirmation means *transport readiness only*; the challenge echo and
request ID are **not authentication, a session credential, or authorization**.
No caller identity, host authenticity, scanner state, or trust is established.

The existing `host.ping` request remains a backward-compatible, read-only
liveness probe before or after a handshake:

```json
{"version":1,"kind":"request","topic":"host.ping","requestId":"example1","payload":null}
```

Its response remains `kind:"response"`, topic `host.ping`, the same request
ID, and payload `{"status":"transport-only","scanAvailable":false}`. Ping
does **not** complete or substitute for the handshake. The process supports
multiple frames until clean EOF. Malformed, oversized, truncated, unknown, or
privileged requests terminate without an output response for the offending
message or user-data diagnostics. Stdout contains only framed protocol bytes.

**Security boundary:** This executable is deliberately **not installed or registered as a browser native messaging host**. PR opener-0614 separately defines the stable host identifier; do not duplicate its identity file or documentation. Browser host manifests, allowed extension identity validation, installation, consent, packaging, native adapters, and scanner coordination are separate checklist tasks. No browser permission or existing browser script is changed here. An arbitrary process can invoke the unregistered binary: ping is *not* authentication, a scanner status, a safe-file verdict or authorization to open any PDF. Browser-supplied origin arguments cannot authorize requests. The host does not access document bytes, paths, scanner processes, quarantine settings, user configurations or launch preferences.

`python3 test-native-messaging-host.py -v` compiles and exercises the actual host process with real framed input and rejection cases. The existing macOS CI build job runs this suite. Deployment must independently authorize the caller and enforce existing ClamAV freshness, document integrity, quarantine and user-selected application gates before enabling privileged operations.
