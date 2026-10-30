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

## Containing-app native messaging registration (opener-0647)

Safari routes `browser.runtime.sendNativeMessage` through its containing
macOS application's native app extension, not an external Chrome/Firefox
host manifest. Xcode embeds `PDFMagicOpenerSafari.appex` under
`PDFMagicOpener.app/Contents/PlugIns`. Its Info.plist specifies
`com.apple.Safari.web-extension` and `SafariWebExtensionHandler`, the
principal class that receives messages under `SFExtensionMessageKey`.

Safari's packaged `extensions/safari/manifest.json` now declares only
`nativeMessaging` as a required permission, while matching the shared
Chromium/Firefox manifest in all other fields. The shared manifest remains
permission-free. The native app extension keeps sandbox-only entitlements,
no website, filesystem, network or app-group access. CI verifies the
Safari-specific manifest exactly in the real .appex and unsigned host ZIP.

This is not a live browser-to-scanner connection. The shared background
script remains inert and sends no native messages; the Safari Swift handler
can only reply to validated `native.status` requests with `status: inactive`,
`scanVerified: false` and `authorizesOpen: false`. No scanner or PDF
opening bridge is added. Installation and activation remain user-controlled;
future authenticated integration needs separate security review. The native
standalone host is not registered with Safari. ClamAV, quarantine, integrity,
verified opening and user preferences remain unchanged.

Apple's documented native messaging route:
https://developer.apple.com/documentation/safariservices/messaging-between-the-app-and-javascript-in-a-safari-web-extension

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
