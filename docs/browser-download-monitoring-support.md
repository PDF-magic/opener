# Browser download monitoring support (opener-1123)

**Current status: PDF Magic Opener download monitoring is inactive in every
browser listed below.** "Supported browser" in the macOS application means
the browser is recognized as a possible *PDF destination*, not that a
monitoring extension is installed, permitted, connected or scanning.

The table distinguishes the availability of browser **download-event APIs**
from PDF Magic Opener's actual integration. A **Documented** row has
vendor-documented download events; **Conditional** means a related API or
Chromium lineage suggests compatibility, but that particular browser/version
still needs live extension testing. **Unverified** means this project has not
established equivalent API/permission behavior. None of those labels is an
assertion that this project's download monitoring works there.

| Browser | macOS bundle ID | Download events API | Current PDF Magic Opener monitoring |
| --- | --- | --- | --- |
| Brave | `com.brave.Browser` | **Conditional** — Chromium-family API; test installed Brave version and permission behavior | **Inactive** |
| Google Chrome | `com.google.Chrome` | **Documented** — Chrome `downloads.onCreated`, `onChanged` and `onErased` | **Inactive** |
| Chromium | `org.chromium.Chromium` | **Conditional** — Chrome's upstream API; verify the particular Chromium build | **Inactive** |
| Microsoft Edge | `com.microsoft.edgemac` | **Conditional** — Edge documents `downloads` API support; verify events and permission on installed Edge | **Inactive** |
| Vivaldi | `com.vivaldi.Vivaldi` | **Conditional** — Chromium-family API; verify installed Vivaldi version | **Inactive** |
| Opera | `com.operasoftware.Opera` | **Conditional** — Chromium-family API; verify installed Opera version | **Inactive** |
| Arc | `company.thebrowser.Browser` | **Conditional** — Chromium-family API; verify installed Arc version | **Inactive** |
| Mozilla Firefox | `org.mozilla.firefox` | **Documented** — Firefox `browser.downloads.onCreated`, `onChanged` and `onErased` | **Inactive** |
| Apple Safari | `com.apple.Safari` | **Unverified** — Safari WebExtension support for these events and optional permission flow must be established in a real Safari build | **Inactive** |

## Why there is no active monitored browser

The [shared extension](../extensions/webextension/README.md) includes an
inert [background entry point](../extensions/webextension/src/background.js)
and a passive [download-event adapter](../extensions/webextension/src/download-monitoring.md).
The Chromium/Firefox manifest and Safari manifest declare an **optional**
`downloads` permission; declaration is **not** a grant. The permission helper
requires a separate trusted user gesture and explicit opt-in, but is not wired
to the active background. The native host is transport-only and does not
provide an authenticated scanner bridge. The native **Enable Browser Download
Monitoring** setting saves a preference; it neither requests permission nor
makes a browser's status "Active".

Even when a future extension has permission, the events merely report
downloads. They do **not** include PDFs displayed inline without a download,
block browser automatic opening, intercept Finder, or verify a PDF is safe.
Real-browser download tests for Chrome, Chromium and Firefox test the browsers'
own download managers, **not** this extension's monitoring.

## Conditions before claiming a browser is supported for live monitoring

An integration must be separately implemented and reviewed. For each browser
and version, test a genuinely installed extension, a user-initiated `downloads`
grant (and refusal/revocation), `onCreated`/`onChanged`/`onErased` events,
complete-file identity, and a trusted authenticated native scan connection.
Only a full clean ClamAV scan with fresh signatures, verified file identity
and integrity, preserved quarantine and the user's selected PDF application
can authorize **PDF Magic Opener's own** handoff. Denied/missing APIs or an
unavailable scanner must fail closed, not silently fall back to unscanned
opening. Do not change the user's existing viewer or download preferences.

For related boundaries see [monitoring limits](download-monitoring-limits.md),
[controlled download opening](download-opening-browser-support.md), and
[real native-download tests](browser-native-pdf-downloads.md).

Primary API references: [Chrome downloads](https://developer.chrome.com/docs/extensions/reference/api/downloads),
[Firefox downloads](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads),
[Edge extension API compatibility](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/api-support),
[Safari WebExtension compatibility](https://developer.apple.com/documentation/safariservices/assessing-your-safari-web-extension-s-browser-compatibility).
