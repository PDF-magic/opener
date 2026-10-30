# Minimum browser permissions (opener-0582, §9.2)

## Current release: none

The shared Chromium Manifest V3 source (`manifest.json`) and its Firefox build
(`dist/firefox/manifest.json`) currently require **no browser API permissions,
host permissions, optional API permissions, or optional host permissions**.
`permissions` and `host_permissions` remain explicit empty arrays; neither
optional field is declared. This is the *minimum*, not a placeholder grant.

The inert toolbar action, static icons, no-op background entry point,
in-extension protocol definitions, user-initiated native preferences link
(scoped separately), and isolated PDF metadata helpers do not justify access
to web pages, downloads, native applications, user data, or network traffic.
The passive `download-monitoring.js` and `scan-pdf-action.js` modules are
**not activated or connected** in the background entry point. The existence
of a module or a browser API does not confer its permission, user consent,
scanner verification, or authority to open any PDF. Safari's native app
sandbox entitlement is separate from WebExtensions API/host permissions.

The machine-readable `permissions-audit.json` records this *review inventory
only*; neither the build nor runtime reads it to request or grant access.

## Conditional permissions for separately reviewed future capabilities

| Capability | Narrowest relevant browser API permission | Now? | Conditions |
| --- | --- | --- | --- |
| Local toolbar, popup, icons, runtime internal messaging | **None** | Inactive or UI-only | No external extension communication or document handling |
| Metadata-only PDF candidate classification | **None** | Library only | Uses caller-provided metadata; does not observe tabs, pages or downloads |
| Download event monitoring | `downloads` | **Not granted** | Only if users opt into a separately implemented listener; no `downloads.open` or all-site access necessary for event monitoring |
| Authenticated browser-to-native app communication | `nativeMessaging` | **Not granted** | Only after a trusted host manifest, extension ID allowlist, authenticated protocol, scanner gate and user authorization are implemented |
| User notifications | `notifications` | **Not granted** | Only if an opt-in notification UI is implemented |
| Persisted extension settings via browser storage | `storage` | **Not granted** | Only when settings persistence and migration are separately implemented |

No current feature needs `tabs`, `activeTab`, `scripting`,
`webRequest`, `cookies`, `history`, `downloads.open`, `<all_urls>`,
`file://` access, broad host origins, or content-script matches. Do not add
those permissions speculatively. If a future reviewed feature truly needs
access to a page or an origin, establish its exact scope and explicit
user-consent flow *at that time*; use optional or per-site access where
supported. Browser engines can differ, so validate the least-privilege
manifest for each target before requesting anything.

The policy is **fail-closed**: changes to any manifest permission or
optional/host-access field require a new scoped task, a documented feature
and consent rationale, and updated CI tests. The current tests assert the
source, Chromium package and Firefox package all retain zero access, and
that Gecko's explicit no-data-collection declaration stays intact. They
run in the required Node `npm test` step in `scanner-tests` CI.

Neither permission inventory nor manifest validation is a malware-clean
verdict. The separate installed scanner's ClamAV freshness, file-integrity,
quarantine and user-selected destination protections remain mandatory.

## Primary browser documentation

- Chrome: https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions
- Chrome downloads API: https://developer.chrome.com/docs/extensions/reference/api/downloads
- Mozilla native messaging: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Native_messaging
- Mozilla extension permissions: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions
