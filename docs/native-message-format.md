# Native messaging JSON protocol v1 (opener-0616)

This defines the **message body only** for future browser-to-native communication.
It does not register a native messaging host, select a transport, install any
manifest, grant `nativeMessaging`, authenticate an extension, or enable scanning.
The native host identifier and host installation are separate checklist tasks.

The native side uses `native_message_format.py` (`encode_native_message` and
`decode_native_message`), matching the envelope already used by
[`extensions/webextension/src/messaging.js`](../extensions/webextension/src/messaging.js).
Both ends must validate messages independently. The body is exactly one
UTF-8 JSON object with five members:

```json
{
  "version": 1,
  "kind": "request",
  "topic": "example.ping",
  "requestId": "request_1",
  "payload": { "example": true }
}
```

- `version`: integer `1` only. Reject unknown versions, booleans and strings.
  Future incompatible versions require separately reviewed negotiation, not
  implicit downgrade or guessed interpretation.
- `kind`: `request`, `response`, or `event`. The kind never grants authority.
  A response should correlate via `requestId`, but no routing is implemented.
- `topic`: 1–80 lower-case ASCII dot-separated segments of `[a-z][a-z0-9]*`.
  Topics are labels, not executable commands. **No topics are registered**.
- `requestId`: 1–80 ASCII letters, digits, underscores or hyphens. It is a
  correlation value, not an authentication credential.
- `payload`: JSON value; null is valid. Only plain, bounded, safe JSON data.

The UTF-8 JSON body must not exceed **16,384 bytes**. Payloads have at most
8 levels of nesting, 512 examined values, 256 entries in an array/object, and
8,192 characters per string. The native codec rejects duplicate keys,
prototype-pollution keys (`__proto__`, `constructor`, `prototype`), non-finite
numbers, integers exceeding JavaScript safe integer range, and unpaired
Unicode surrogates. Invalid UTF-8, unknown/missing fields, malformed IDs,
trailing bytes and unexpected versions fail closed with a path-free error.

**Transport boundary:** Native messaging's length-prefixed framing, host
installation, sender authentication, permissions, protocol routing and
connection lifetime belong to separate tasks. `encode_native_message` returns
only the JSON body bytes, not a framing header. The extension's background
worker stays inert and the manifest does not request native messaging access.

**Security boundary:** No message authorizes opening or scanning. Payload
claims such as `scanVerified` or `authorizesOpen` are untrusted. A future
reviewed handler must independently enforce ClamAV signatures and freshness,
integrity, quarantine, mandatory scanning and the user's selected PDF app.

Verification: `python3 test-native-message-format.py -v` tests limits,
malformed input, version rejection and real JS/Python codec interoperation
using Node.js 22. GitHub `scanner-tests` runs this suite on every PR.
