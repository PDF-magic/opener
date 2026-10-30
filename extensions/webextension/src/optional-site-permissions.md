# Optional, per-site browser permissions (opener-0587)

The extension presently needs **no website host access**. Both Chromium and
Firefox manifests retain `host_permissions: []` and do not declare
`optional_host_permissions`, so the helper in `optional-site-permissions.js`
will **not request any site permissions** in the current product.

If a future, separately approved feature genuinely needs website-specific
access, prefer a Manifest V3 `optional_host_permissions` entry for **only the
exact HTTPS hostname** rather than required `host_permissions` or broad
`<all_urls>`/wildcard origins. Browser support varies: modern Chromium and
Firefox support optional host declarations, but an unsupported browser must
not cause a fallback to install-time or all-site access.

Future integrations may import `requestOptionalSitePermission` and invoke it
*directly from an explicit user-click handler*, with an already-reviewed
manifest declaring the matching optional site, a trusted `permissions` API,
`siteFeatureEnabled: true`, `userInitiated: true`, and an exact canonical
`siteOrigin` (such as `https://docs.example.org/`). The helper requests exactly
one `origins: ["https://docs.example.org/*"]`, then verifies the effective
grant through `permissions.contains()`. It returns one frozen, path-free state:
`granted`, `denied`, or `unavailable`. All states have `authorizesOpen: false`;
only a currently verified result has `sitePermissionVerified: true`.

The helper refuses unknown, wildcard, HTTP, file, localhost/IP, path-bearing,
noncanonical, unrelated, undeclared or required-only host permissions. It
performs no browser detection by user agent, background registration,
network request, file access, native messaging or scanner action, and fails
closed when optional permission APIs are absent or callback-only. The actual
caller must bind the permission request to the browser's trusted user gesture;
passing a boolean is **not** a substitute for this requirement.

A verified grant is only a snapshot. Future runtime code must check revocation
and sender origin before accessing resources. Web page permissions, native
scanner readiness, ClamAV freshness, quarantine decisions and user-selected
PDF application handling are independent security gates. Site consent never
constitutes a safe-PDF verdict or an authorization to scan/open documents.

This separate helper intentionally does **not** change the broader
host-permission inventory (opener-0585), conditional `downloads` API access
(opener-0583), or local native-messaging prerequisites (opener-0584).
`tests/optional-site-permissions.test.mjs` runs automatically in the existing
required Node WebExtensions CI step, covering supported and unsupported
browsers and the unchanged current manifests.

Primary references:
- https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/optional_host_permissions
- https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/permissions/request
