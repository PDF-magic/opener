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

### Scan-request message (opener-0628)

After a successful `host.handshake` on the **same native host process**, a
caller may express manual scan intent using a bounded v1 request:

```json
{"version":1,"kind":"request","topic":"scan.request","requestId":"scan_1","payload":{"intent":"user-selected-pdf"}}
```

The payload must contain **exactly one** string field, `intent`, equal to
`"user-selected-pdf"`. It deliberately contains **no local file path, URL,
download ID, file bytes, claimed verdict, profile override, or authority
token**. A caller's declaration of manual intent is not proof of a user
gesture or of a trusted file selection.

Until a separately authenticated and reviewed native coordinator is installed,
the host emits a **correlated rejection** with the same `requestId`:

```json
{"version":1,"kind":"response","topic":"scan.request","requestId":"scan_1","payload":{"status":"unavailable","reason":"trusted-scan-coordinator-required","scanAvailable":false,"scanStarted":false,"scanVerified":false,"authorizesOpen":false}}
```

This is a defined message exchange, **not scan execution or scan submission**.
It does not enqueue or launch a scanner, open files, access the filesystem,
record paths, create persistent state or change user preferences. A valid
request may be repeated; every reply remains unavailable. Scan requests
before the connection handshake, malformed payloads, unsupported versions,
extra fields and the older `pdf.scan` topic fail closed without a response.
The host still does not register itself with browsers, request extension
permissions or authenticate the caller. **A handshake is not sufficient
authentication** for scanning.

Enabling actual scans is a separate integration task requiring authenticated
extension identity, an explicit trusted user-selected local file, the existing
mandatory ClamAV and signature freshness gate, file integrity and quarantine
checks, verified destination handoff, and safe cancellation/results. No browser
input may weaken these checks; no message is proof a PDF is clean.

### Scan-status message (opener-0629)

A caller can ask about a scan-request correlation identifier after completing
`host.handshake` on the **same native host connection**:

```json
{"version":1,"kind":"request","topic":"scan.status","requestId":"status_1","payload":{"scanRequestId":"scan_1"}}
```

The `scanRequestId` is the bounded, 1–80 character ASCII identifier from
the earlier `scan.request` **requestId** (letters, digits, underscore, or
hyphen). It is a correlation value only, **not proof the scan exists**.
The status query's own `requestId` correlates this response independently.
The payload must contain **exactly** `scanRequestId`; local paths, URLs,
download IDs, caller-supplied verdicts, progress values, policy overrides,
or extra fields are rejected without responding.

Until an authenticated, trusted scanner coordinator exists, `scan.request`
never launches a job. Every well-formed status query—whether or not it
refers to an earlier rejected request—therefore returns this truthful
unavailable state:

```json
{"version":1,"kind":"response","topic":"scan.status","requestId":"status_1","payload":{"scanRequestId":"scan_1","status":"unavailable","reason":"trusted-scan-coordinator-required","scanAvailable":false,"scanStarted":false,"scanVerified":false,"authorizesOpen":false}}
```

A successful handshake and a matching request ID are **not** evidence of
authorization, a running scan, a verified clean result, or permission to open
a PDF. The native host does not read files, query a scanner, invent
completion percentages, maintain a cross-process job registry, or alter
user preferences. Requests before handshake, malformed IDs, extra payload
keys and unsupported message kinds/versions fail closed without a status
response. The response is intentionally not an actual scanner verdict.

A later separately reviewed integration must authenticate the caller and
coordinate trusted user-selected local files, active scan lifecycle,
cancellation, ClamAV freshness and mandatory checks, file integrity,
quarantine, and verified opening before it can expose real job states.
Neither message alone may weaken the existing scanner safeguards.

### Scan-result message (opener-0630)

After a successful `host.handshake` on the **same native host process**,
a caller may query the result of a scan-request correlation identifier:

```json
{"version":1,"kind":"request","topic":"scan.result","requestId":"result_1","payload":{"scanRequestId":"scan_1"}}
```

The `scanRequestId` is a bounded, 1–80-character ASCII identifier (letters,
digits, underscore, hyphen) corresponding to a `scan.request` envelope's
`requestId`. It is **not proof** that a scan was accepted, started or
completed. The envelope's own `requestId` independently correlates the
result query. The payload has exactly one key, `scanRequestId`; caller-supplied
verdicts, file paths, scan diagnostics, file bytes, policy overrides, progress
values or any extra field are rejected.

Because `scan.request` is currently *always unavailable* (there is no
authenticated trusted scanner coordinator), **no native scan result exists**.
For both known and unknown IDs, the host must return an explicit null result
and must not fabricate a clean or failed scan:

```json
{"version":1,"kind":"response","topic":"scan.result","requestId":"result_1","payload":{"scanRequestId":"scan_1","status":"unavailable","reason":"trusted-scan-coordinator-required","result":null,"scanCompleted":false,"scanVerified":false,"authorizesOpen":false}}
```

`result: null` distinguishes **absence of any verified scan result** from
a scan failure, detection, cancellation, or completion. Canonical terminal
outcomes are defined by the separately enforced scanner in
`scan_results.py` (`clean`, `malwareDetected`, `incompleteScan`, etc.);
**none is assigned by this unregistered native host**. A scan-result message
can never replace the scanner's separate verified evidence and PDF-opening
gate, even if a future implementation reports `clean`.

The handshake does not authenticate a caller. The host does not retain jobs,
inspect source files, invoke a scanner, read diagnostics, or authorize opening.
Malformed requests, pre-handshake queries, unsupported kinds or versions,
or attempted caller-injected results fail closed without a result response.
Real result delivery requires a separately reviewed, authenticated scanner
coordinator enforcing explicit file selection, ClamAV freshness, complete
scanning, file integrity, quarantine, cancellation and verified handoff.

### Scan-cancellation message (opener-0631)

After a successful `host.handshake` on the **same native host process**,
the caller may send a cancellation request correlated to an earlier scan
request ID:

```json
{"version":1,"kind":"request","topic":"scan.cancel","requestId":"cancel_1","payload":{"scanRequestId":"scan_1"}}
```

The `scanRequestId` is a 1–80-character ASCII identifier consisting of
letters, digits, underscore or hyphen, corresponding to the earlier
`scan.request` envelope's `requestId`. It does **not** prove that any job
was accepted or that the sender owns it. The cancellation envelope's own
`requestId` independently correlates the reply. The payload must contain
**exactly one** field, `scanRequestId`. Arbitrary process IDs, signals,
paths, URLs, claimed results, permission changes or extra fields are rejected.

As in `scan.request`, `scan.status`, and `scan.result`, the standalone host
has **no authenticated scanner coordinator or active native scan jobs**.
It must not claim that cancellation succeeded or modify a real scanner
process. Each valid cancellation message, even when repeated or referring
to an unknown scan ID, receives:

```json
{"version":1,"kind":"response","topic":"scan.cancel","requestId":"cancel_1","payload":{"scanRequestId":"scan_1","status":"unavailable","reason":"trusted-scan-coordinator-required","cancellationAccepted":false,"cancelled":false,"scanStarted":false,"scanVerified":false,"authorizesOpen":false}}
```

`cancelled:false` and `cancellationAccepted:false` are deliberate:
they distinguish **no cancellation occurred** from a confirmed
cancellation or a scan failure. No completed scan result, clean verdict
or PDF-opening authorization is implied. A cancellation request does not
change subsequent `scan.status` or `scan.result` responses, spawn a
process, kill a caller-specified PID, change user preferences or touch any
PDF. Pre-handshake and malformed requests fail closed with no response or
diagnostic output.

The application's *existing* scanner subprocess cancellation controls
remain independent. Connecting them to browser native messaging is a
separate security-reviewed task requiring caller authentication, trusted
file selection, authorization to cancel **only that caller's active job**,
cancellation/cleanup lifecycle handling, and preservation of mandatory
ClamAV freshness, integrity, quarantine and verified-opening protections.
The host handshake alone is not authorization.

### Health-check message (opener-0632)

After completing the version-1 `host.handshake` on the same native host
process, a caller can perform a separate, read-only health check:

```json
{"version":1,"kind":"request","topic":"host.health","requestId":"health_1","payload":null}
```

The response correlates the same request ID and reports only facts the
transport-only process can truthfully establish:

```json
{"version":1,"kind":"response","topic":"host.health","requestId":"health_1","payload":{"status":"transport-only","transportResponsive":true,"scannerHealth":null,"scanAvailable":false,"authorizesOpen":false}}
```

`transportResponsive:true` means this process successfully answered a
framed request, **not** that ClamAV, its signatures, a scanner coordinator,
an application installation, or document opening is healthy or available.
`scannerHealth:null` means **not evaluated**, not healthy or clean.
No scanner is started or inspected, no files or user settings are accessed,
and no authorization is granted. Unlike the pre-handshake `host.ping`
liveness probe, `host.health` requires a completed handshake, but the
handshake itself is not browser authentication. Only a `null` payload is
accepted; caller-supplied paths, verdicts, readiness flags and extra fields
fail closed without a response for that message. Health checks can be
repeated on the established connection and cannot mutate scan or cancellation
state. The existing compiled-host macOS CI suite exercises these cases.

### Native request rate limit (opener-0664)

The standalone host enforces a fixed **maximum of 64 complete native request
frames in any rolling two-second window per host process**. The bound is
checked *after* reading a framed request but *before* parsing its JSON or
dispatching a handler, so ordinary pings, handshakes, status lookups and
unavailable scan operations all consume the same budget. The limiter uses
monotonic process uptime and stores at most 64 timestamps; it neither waits
nor allocates an unbounded queue. A 65th frame inside the window terminates
that native host process **without an error response or stderr diagnostics**.
Previously emitted valid responses remain framed and unchanged.

The rolling window expires naturally during an otherwise healthy, long-lived
connection, preserving normal use of `host.health`, `host.ping` and the
existing handshake. Rate limiting does **not** indicate a scan failure, a
scanner verdict or authorization to open a PDF. A new native host process has
a new independent budget; this is a **per-connection abuse limit**, not a
cross-process or per-user quota. Caller authentication and browser-side
controls are separate security requirements, and native messaging remains
transport-only. No scanner, policy preferences, file access or registration
manifests are modified.

The compiled-host tests cover over-limit termination, correct response
framing, independent new connections, and replenishment after the sliding
window. They run in the existing `macos-build` CI job via
`python3 test-native-messaging-host.py -v`.

### Communication deadlines (opener-0634)

The standalone host enforces cumulative monotonic deadlines on its native
messaging pipes: **10 seconds** to receive the first byte of each request
(including the first request), **5 seconds** to finish its length prefix and
bounded JSON frame after that first byte, and **5 seconds** to write the full
framed response. Partial reads, slow byte-by-byte senders, blocked stdout
pipes, repeated interrupted system calls, and idle peers cannot extend those
deadlines. Completion of one message starts a fresh deadline for the next.
Normal complete messages and clean EOF between frames remain supported.

A timeout terminates the connection **fail-closed** with no timeout response
or stderr diagnostics, and a new native host process starts without the
previous handshake state. A receiver must discard any incomplete response
frame following a failed connection; no transport success, partial message
or timeout implies a clean scan, verified cancellation, or permission to
open a PDF. Timeouts are fixed safety limits, not caller-configurable
scanner settings. This host remains transport-only and unregistered.

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

### Validate all supplied native registration paths (opener-0655)

The current native messaging host **does not accept any browser-supplied PDF
file path**. Only a trusted local coordinator with independent file-selection
proof could add that capability. Existing `scan.request`, status, result and
cancel contracts continue to reject file paths and never scan or open PDFs.

The executable paths accepted by the current Chrome and Firefox per-user
registrars and the read-only host discovery verifier are validated as absolute,
canonical local paths with bounded UTF-8 length, no control characters or
traversal components, no symlinked executable or ancestor directory, and an
existing regular executable with OS execute permission. Home and registration
directory paths are likewise checked before use. The uninstall helper validates
the original exact executable path (including any existing ancestors) without
requiring the executable to survive uninstall; it still refuses customized
manifests and preserves unrelated user registrations.

All invalid inputs fail closed. These changes do not grant any extension
permission, authenticate a scanner, change ClamAV/quarantine policy, or modify
PDF opening and user-selected destinations. Real PDF path admission is an
independent prerequisite of any future privileged scan coordinator.

### Executable-launch boundary (opener-0657)

The native messaging host enforces an explicit fixed `approvedTopics` allowlist
before its per-topic payload checks. Unknown requests to execute programs,
launch shells, run processes, open applications or handle unreviewed command
topics fail closed. Approved topics retain their exact payload validation;
caller-supplied executable paths, process IDs, argv and shell scripts are not
accepted. The host does not expose process-launch APIs to native messages.

This is not browser authentication. A valid handshake never enables scanning.
Existing ClamAV signature freshness, verified scan evidence, integrity,
quarantine, opening authorization and user-configured PDF application settings
remain separately enforced and unchanged.

The existing macOS CI compiled-host suite `python3 test-native-messaging-host.py -v`
exercises executable selection across unknown topics and approved payloads
using a real executable canary, confirms rejection without launching it, and
checks a fresh connection still returns truthful scan unavailability. It also
guards `Host.swift` against common process and application-launch APIs.
