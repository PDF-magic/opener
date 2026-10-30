# Controlled opening of downloaded PDFs by browser (opener-0712)

**Status on 2026-10-30: no browser has an active PDF Magic Opener
download-opening integration.** The shared WebExtension's background is inert,
its popup says **Not active**, and the shared manifest requests no
`downloads.open` or native messaging permission. The separately packaged
Safari extension declares `nativeMessaging` but its native handler is
transport-only; it does not authorize scans or openings. The opt-in
[Open After Scanning action](../extensions/webextension/src/download-open-after-scanning.md)
is a reusable *user-intent interface*, **not** an enabled opening command.
This document distinguishes *vendor-supported browser APIs* from an actually
installed, authorized, tested **PDF Magic Opener controlled-opening flow**.

## Three distinct meanings of “open”

1. **Browser-owned opening:** A download shelf, downloads page, PDF viewer,
   auto-open setting, administrator policy or third-party extension can open
   or preview a PDF. These paths belong to the browser. Merely observing
   `downloads.onChanged` **does not intercept or veto** them, and a browser
   may display a PDF inline without ever creating a completed download.
2. **Extension-invoked opening:** Chrome/Chromium and Firefox document
   `downloads.open(downloadId)` for a *completed* download. It needs both
   `downloads` and `downloads.open` permissions **and a direct user
   gesture**. It hands the downloaded file to the system-associated
   application; it does **not** choose the app, certify the file, delay the
   browser's own opening, or guarantee an inline PDF tab. In particular, a
   delayed, asynchronous "scan finished" callback does not itself supply a
   user gesture. PDF Magic Opener deliberately **does not request or use**
   this API. A future implementation must not use it to bypass the native
   verified application preference.
3. **Native verified application handoff (preferred for this project):** The
   macOS [scan gate](../scan-and-open.py) separately enforces an actual
   complete clean ClamAV result, fresh signatures, current file identity,
   content integrity, quarantine retention and the user's selected
   [verified PDF target](../verify-pdf-target.swift). The
   [native launcher](../launch-scanned-file.swift) then performs the
   application handoff. This is a capability of the *native application*,
   not proof that a browser allows an extension to prevent **other** opening
   paths. The native destination can be one of the registered browser bundle
   IDs below **if installed and independently verified**, or a user-selected
   compatible application.

## Browser-by-browser support matrix

**Reading the table:** "Documented" means a vendor documents the underlying
download API, **not** that PDF Magic Opener has implemented or tested
controlled opening there. "Conditional" means shared Chromium lineage or
API-family support makes a future integration plausible, but the precise
`downloads.open` behavior must be verified on that browser and version.
"Unverified" means no source here establishes the required API. Every row's
**PDF Magic Opener flow is currently inactive**. These are macOS bundle IDs
from the [browser registry](../browser_registry.py), not a browser
installation probe or authorization allowlist.

| Browser | macOS bundle ID | Extension `downloads.open` route | Verified native handoff | Current PDF Magic Opener download-opening flow |
| --- | --- | --- | --- | --- |
| Brave (default) | `com.brave.Browser` | Conditional — Chromium-derived; verify version, permission, gesture and browser policies | Conditional on installed, verified PDF target | Inactive |
| Google Chrome | `com.google.Chrome` | **Documented** — Chrome `downloads.open`, completed file, `downloads` + `downloads.open` and user gesture | Conditional on installed, verified PDF target | Inactive |
| Chromium | `org.chromium.Chromium` | Conditional — upstream Chromium download API; verify this build | Conditional on installed, verified PDF target | Inactive |
| Microsoft Edge | `com.microsoft.edgemac` | Conditional — Edge documents `downloads` API support; verify `open`, permission and gesture in installed Edge | Conditional on installed, verified PDF target | Inactive |
| Vivaldi | `com.vivaldi.Vivaldi` | Conditional — Chromium-derived; verify this browser's API and settings | Conditional on installed, verified PDF target | Inactive |
| Opera | `com.operasoftware.Opera` | Conditional — Chromium-derived; verify this browser's API and settings | Conditional on installed, verified PDF target | Inactive |
| Arc | `company.thebrowser.Browser` | Conditional — Chromium-derived; verify this browser's API and settings | Conditional on installed, verified PDF target | Inactive |
| Mozilla Firefox | `org.mozilla.firefox` | **Documented** — Firefox `browser.downloads.open`, completed file, `downloads` + `downloads.open` and user action | Conditional on installed, verified PDF target | Inactive |
| Apple Safari | `com.apple.Safari` | **Unverified** — do not assume Safari implements `downloads.open` or Chrome's event semantics | Conditional on installed, verified PDF target; containing-app native messaging is distinct from a browser download-open API | Inactive |

The Chromium browser packaging, Edge smoke test, Firefox manifest checks and
Safari embedded-extension build establish **packaging or inert UI behavior**,
not a live `downloads.open` or native scanner-to-browser integration.
Chrome Web Store compatibility is not evidence of API/permission parity in
Brave, Vivaldi, Opera or Arc. Safari's WebExtension model is not evidence
that the specific downloaded-file opening method exists. The native bundle
registry allows custom app selection; it does not claim every listed
browser can open a PDF in-tab.

## What can actually be enforced?

- **Possible once separately implemented and verified:** an explicit
  *Open After Scanning* action attached to one authenticated native scan
  session. An accepted user request is only a queued intent; a trusted
  native coordinator must revalidate the scanner's **final** clean verdict,
  the unchanged local file and the saved target application immediately
  before handoff. The existing
  [one-opening-command gate](../extensions/webextension/src/download-open-command-once.md)
  prevents repeated requests within one trusted session. A reopened native
  session still needs independent idempotence and reconciliation.
- **Not guaranteed by any listed browser integration:** blocking automatic
  PDF viewing, operating-system open actions, other extensions or
  browser-controlled download UI. A browser may bypass the extension's
  chosen workflow; extension download-event access is **observational**.
  Do not advertise “all PDFs are scanned before any browser open” based
  on this table, or silently change the user's viewer/download preferences.
- **Never bypass:** native ClamAV signature freshness, full scan evidence,
  file stability and canonical identity, existing browser malware warnings,
  macOS quarantine, application identity, selected application preference,
  and required user consent. A browser's `danger: "safe"`, `exists: true`,
  a filename, successful extension build or host handshake is **not** an
  opening authorization. An unavailable, interrupted, incomplete, suspicious
  or malicious result must remain blocked within the native-controlled route.
- **Do not attempt to manufacture a user gesture** or invoke
  `downloads.open` from a later asynchronous result. A future
  browser-specific user-gesture route would require separate explicit
  permission review and real browser acceptance tests.

## Acceptance checks before claiming controlled opening

For **each** browser on a disposable test profile: verify the actual
installed version and extension distribution/signing, permission prompts
(`downloads`, `downloads.open` only if a separately approved flow uses
it), the user gesture requirement, event availability and completion/ID
correlation, native host admission, scanner result identity and cancellation,
quarantine retention, and final launch in the user's selected application.
Exercise inline PDF viewing, browser auto-open settings, blocked dangerous
downloads, changed/missing files, profile isolation, and third-party
extensions as **independent escape paths**. An unsupported API or denied
permission must disable the proposed action, not launch through an
unverified fallback. Real browser end-to-end tests are still required;
unit tests cannot certify browser-enforced prevention.

## Primary vendor references

- [Google Chrome downloads API — open, permissions and user gesture](https://developer.chrome.com/docs/extensions/reference/api/downloads)
- [Firefox WebExtensions downloads.open](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads/open)
- [Firefox WebExtensions user actions and asynchronous gesture limits](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/User_actions)
- [Microsoft Edge extension API support](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/api-support)
- [Apple Safari Web Extensions integration model](https://developer.apple.com/documentation/SafariServices/safari-web-extensions)

These are *vendor API references*, not evidence of a released PDF Magic
Opener extension, a tested installed browser, or browser-wide PDF
interception. Also see [viewer differences](browser-pdf-viewers.md) and
[extension distribution status](browser-extension-distribution.md).
