# Native messaging host executable (opener-0615)

`Host.swift` is a **standalone native executable source** for macOS. Build it with the system Swift compiler:

```sh
xcrun swiftc -O -parse-as-library -warnings-as-errors native-messaging/Host.swift -o /path/to/pdf-magic-native-host
```

The output is a real process executable, not a browser extension or PDF handler. It speaks browser native messaging transport: a 32-bit little-endian byte length followed by UTF-8 JSON on standard input, and the same framing on standard output. Frames are bounded to 16 KiB, matching the shared WebExtensions message envelope.

The **only** accepted request is this exact envelope with a 1–80 character ASCII `requestId`:

```json
{"version":1,"kind":"request","topic":"host.ping","requestId":"example1","payload":null}
```

The response uses `kind:"response"`, topic `host.ping`, the same request ID and payload `{"status":"transport-only","scanAvailable":false}`. The process handles multiple frames until clean EOF. Malformed, oversized, truncated, unknown, or non-ping requests terminate without an output response or user-data diagnostics. Stdout contains only framed protocol bytes.

**Security boundary:** This executable is deliberately **not installed or registered as a browser native messaging host**. PR opener-0614 separately defines the stable host identifier; do not duplicate its identity file or documentation. Browser host manifests, allowed extension identity validation, installation, consent, packaging, native adapters, and scanner coordination are separate checklist tasks. No browser permission or existing browser script is changed here. An arbitrary process can invoke the unregistered binary: ping is *not* authentication, a scanner status, a safe-file verdict or authorization to open any PDF. Browser-supplied origin arguments cannot authorize requests. The host does not access document bytes, paths, scanner processes, quarantine settings, user configurations or launch preferences.

`python3 test-native-messaging-host.py -v` compiles and exercises the actual host process with real framed input and rejection cases. The existing macOS CI build job runs this suite. Deployment must independently authorize the caller and enforce existing ClamAV freshness, document integrity, quarantine and user-selected application gates before enabling privileged operations.
