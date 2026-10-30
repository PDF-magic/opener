# Inspect browser-specific native messaging host discovery (opener-0648)

Use the **read-only**, per-browser verifier to inspect whether a reviewed host
manifest appears at that browser's candidate native host lookup path.
This does not install anything or start a browser, executable, scanner or PDF.

~~~sh
node native-messaging/verify-host-discovery.mjs --browser chrome --extension-id ACTUAL_APPROVED_EXTENSION_ID
node native-messaging/verify-host-discovery.mjs --browser firefox --extension-id pdf-magic-opener@example.invalid
node native-messaging/verify-host-discovery.mjs --browser chrome-for-testing --browser-major 146
~~~

Supply the real installed browser/version and **already approved** extension ID.
The verifier reads an existing manifest, validates the canonical name, stdio
transport, absolute executable, exact allowlist and matching extension identity,
and refuses symlinked registration locations. It never alters user data.
The browser's directory is selected separately for Google Chrome, Chromium,
Microsoft Edge, Brave, Vivaldi, Arc and Firefox. Opera's published macOS lookup
uses Chrome's location. Chrome for Testing moved to a distinct location with
major version 146; its version is mandatory to prevent guessing. Firefox also
supports the standard Linux per-user location. Other platforms are rejected.

The machine-readable statuses are `unregistered`, `unsafe`, `invalid`,
`registration-valid`, and `candidate-registration-valid`. **None means a
browser handshake was observed.** Brave, Vivaldi and Arc use third-party
integration-reference paths that require independent verification in a real
installed browser; those are explicitly reported as candidates. Published
browser paths establish expected on-disk registration only. To prove actual
runtime discovery, an approved extension with the `nativeMessaging` permission
must send a transport-only `host.ping`/handshake through that exact installed
browser and receive the expected correlated response. That end-to-end step is
currently blocked by the inactive WebExtensions manifest (which intentionally
lacks `nativeMessaging`) and missing reviewed browser-to-host authentication.
**Do not** bypass that permission/authentication boundary to obtain a pass.

This verifier does not replace the registration tasks (Chrome opener-0639,
Chromium-family opener-0643, Firefox opener-0644), nor does it silently extend
their coverage. A present manifest cannot prove that ClamAV ran or a PDF may
be opened. Mandatory scanner freshness, integrity, quarantine, verified
opening and user preferences stay unchanged.

`extensions/webextension/tests/native-host-discovery.test.mjs` exercises
isolated temporary directories for each lookup, Chrome/Opera sharing,
Chrome-for-Testing version divergence, Firefox's different manifest schema,
malicious manifests, symlink refusal and no authorization changes. The existing
`npm test` required GitHub CI job executes the test without touching any real
browser installation or profile.
