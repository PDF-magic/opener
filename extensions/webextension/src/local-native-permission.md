# Local-only native messaging permission (opener-0584)

`requestLocalNativeMessagingPermission({ permissionsApi, manifest, localHost, userInitiated })`
is a **dormant, browser-neutral helper**, not a working browser-to-native bridge. It never
registers a native host, sends a native message, scans or opens a file, migrates settings,
or requests a permission at import time.

**Current behavior:** the inactive extension's Chromium and Firefox manifests have
`permissions: []`, `host_permissions: []`, and **no** `optional_permissions`.
There is no separately registered/authenticated browser-to-native host yet, so
requests are denied before browser APIs are called. The Safari target shares
this inactive manifest. The WebExtensions host registration, a trustworthy
local-only integration approval flow and the active native scanner transport
are prerequisites of any later request and require separate review.

For future *verified local* integrations only, a separately reviewed build may
declare `optional_permissions: ["nativeMessaging"]` (never a required
install-time grant). The caller must independently verify native host registration,
select a trusted installed local host identifier, and call this helper directly in
an actual user gesture (such as a deliberate button click), with a current browser
manifest and a Promise-style `permissions.request` API:

```js
// Illustrative future integration — not wired into the inactive extension.
function onLocalIntegrationButtonClicked() {
  return requestLocalNativeMessagingPermission({
    permissionsApi: trustedExtensionPermissions,
    manifest: trustedExtensionManifest,
    localHost: { name: verifiedRegisteredLocalHostName, registrationVerified: true },
    userInitiated: true
  });
}
```

A caller-provided `registrationVerified` assertion is **not authentication**.
The caller must verify the installed host manifest and browser's allowed extension
identity through a separately reviewed trusted integration path. The helper
performs only a narrow consent request for the exact `nativeMessaging` permission.
It does not grant the right to connect to arbitrary applications, and a `granted`
result does not imply an authenticated native session, safe document or scanner
approval. Browser/user denial, unavailable optional permission and errors all
fail closed without leaking native paths or other diagnostic details. The
browser can revoke an optional permission later; future integration must check
its current grant immediately before every privileged operation.

The call invokes `permissions.request()` synchronously (before awaiting) so the
browser's direct user-gesture requirement is retained. Only Promise-style
WebExtensions APIs are supported (modern Chromium MV3 and Firefox). Unsupported
callback-only APIs fail closed; this avoids unreviewed asynchronous prompting.

The installed ClamAV freshness checks, file-integrity and quarantine controls,
and user-selected PDF destination remain mandatory and wholly outside the
permission-request helper. Existing permissions audit (opener-0582) remains the
source of truth for the current zero-privilege scaffold.

`npm test` automatically runs `tests/local-native-permission.test.mjs` as part
of the required shared WebExtensions CI suite.
