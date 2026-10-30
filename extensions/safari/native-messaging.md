# Safari native messaging adapter (opener-0610)

Safari's `SafariWebExtensionHandler` reads `SFExtensionMessageKey` from
the first `NSExtensionItem`, validates the shared version-1 envelope, and
returns an envelope inside a new `NSExtensionItem`. The only accepted message
is a `request` with topic `native.status`, a bounded ASCII `requestId`,
a null payload, exactly five envelope fields and at most 16 KiB of JSON.

The sole possible native response has matching `version`, `topic`, and
`requestId`, `kind: response`, and this payload:

```json
{"status":"inactive","scanVerified":false,"authorizesOpen":false}
```

Unsupported, oversized or malformed requests return **no response items**.
The handler never echoes caller-supplied payloads, paths, URLs or profile
identifiers and never requests file access, reads scan results, opens PDFs,
calls the host application, or changes user preferences.

This is a **dormant, read-only adapter**. Safari requires the
`nativeMessaging` manifest permission for a JavaScript sender; the shared
manifest deliberately does not declare it. The background script has no
listeners or senders. Native host registration and any authorized
browser-to-scanner workflow are separately reviewed tasks. No file, app
group, network or scanner privilege was added; ClamAV, quarantine, and
verified PDF opening gates remain unchanged.

Run the platform-neutral behavior checks with:

```sh
swiftc -parse-as-library -warnings-as-errors \
  extensions/safari/SafariWebExtensionHandler.swift \
  test-safari-native-messaging.swift -o /tmp/test-safari-native-messaging
/tmp/test-safari-native-messaging
```

The existing `test-safari-extension-target.py -v` suite invokes this Swift
test automatically on macOS as part of the established CI build and checks
its source invariants on all runner platforms. No duplicate CI workflow
configuration is needed.
