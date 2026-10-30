# Host permission scope — opener-0585 (section 9.2)

## Decision: zero host permissions are necessary

The present Chromium, Firefox, and packaged Safari WebExtensions scaffold
requires **no host origins**. The shared source manifest explicitly declares
`"host_permissions": []` and **does not** declare
`optional_host_permissions`, `content_scripts` or host match patterns. The
Firefox packaging step retains the same host scope. The audited decision is
recorded in `host-permissions-audit.json`, which grants **nothing**; the file
is review metadata, not a manifest, settings file, or runtime permission
request. A host permission is a grant to access data at a matched website
origin, not a prerequisite for running the extension itself.

| Existing or separately planned function | Host origin required? | Why |
| --- | --- | --- |
| Static browser toolbar, popup, bundled icons | **No** | Local extension assets, no page injection or web requests |
| Observe extension update events | **No** | Local extension runtime events, not website data |
| Observe browser-managed download events | **No** | Uses the separate `downloads` API permission when independently implemented and authorized; it does not need host origins just to observe events |
| Detect PDF candidates from caller-supplied metadata | **No** | Offline string processing; no page reading or URL fetching |
| Internal extension message envelopes | **No** | No remote host is contacted or inspected |
| Talk to a trusted installed native scanner | **No** | Would require a separately reviewed `nativeMessaging` API permission and an authenticated host integration, **not** permission to inspect websites |
| User-initiated local native preferences link | **No** | A fixed local app URL, not access to any website origin |

**Current state:** The background entry point is deliberately inert. The
download monitor, native Scan PDF action, and initialization modules are
reusable contracts, **not active permission-using integrations**. This
analysis does not claim that scanner or native messaging capabilities are
currently connected. Neither browser download metadata nor a manifest build
is a malware-clean verdict or authorization to open a PDF.

## When an origin could become necessary

A *future* independently reviewed feature that injects content scripts into
specific websites, reads their page DOM, or fetches PDF resources from
restricted web origins may need scoped host permissions. First identify the
actual sites and operation, avoid blanket `<all_urls>`, and obtain the
user's informed permission (using optional/per-site grants when supported).
A future request to **start a new remote download** requires its own API
and network-access review; the passive download event adapter does not
justify that access now.

Neither a direct `file://` host grant nor `http://*/*`,
`https://*/*`, `*://*/*`, or `<all_urls>` is justified for the current
work. Do not add `tabs`, `scripting`, `webRequest`, `cookies`, or
origin match patterns to make an unimplemented feature appear available.
Browser API permissions (`downloads`, `nativeMessaging`, `storage`, etc.)
and host-origin permissions are distinct; see the separate section 9.2
minimum **API** permission inventory in PR #377. The native macOS sandbox
entitlements are also separate from WebExtensions host permissions.

The least-privilege scope is enforced in
`tests/host-permissions.test.mjs` for source and built Chromium and Firefox
manifests. The existing required CI `scanner-tests` job runs these checks
with `npm test`. Any future change to host access requires a new scoped PR,
an exact-origin rationale, consent and browser compatibility review, and
updated CI regression coverage. This audit does **not** change the native
scanner's ClamAV freshness, file integrity, quarantine or destination gates,
or any saved user customization.

### Primary browser documentation

- Mozilla: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/host_permissions
- Mozilla: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions
- Chrome: https://developer.chrome.com/docs/extensions/reference/api/downloads
- Mozilla: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging
