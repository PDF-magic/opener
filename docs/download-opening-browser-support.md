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

## Strict pre-open interception availability (opener-0717)

**Definition:** "strict interception" means a browser extension can reliably and
synchronously prevent **every** browser-owned or OS-controlled PDF opening
(inline viewer, downloads shelf, auto-open, other extensions and Finder) until
a particular completed native scan and integrity verification succeeds.
Merely receiving a download event, changing the target filename, opening
a file from an extension, or safely controlling **only PDF Magic Opener's own**
native handoff does not meet this definition.

**Result:** None of the nine supported macOS browser entries has a
**documented public WebExtensions downloads API** providing that universal,
pre-open veto. This is a finding about the browser extension APIs available
for this project, **not** a proof that all possible privileged OS controls,
enterprise policies or custom browser builds are technically impossible.
Safari's relevant API coverage remains unverified and must **not** be
relabelled as a confirmed implementation or a proven impossibility.

| Browser | Strict interception via standard extension download APIs | Independent opening path not covered |
| --- | --- | --- |
| Brave (default) | **Unavailable** — Chromium-family API; no documented universal pre-open veto; specific version unverified | Download shelf, embedded PDF viewer, OS opening |
| Google Chrome | **Unavailable** — documented Chrome downloads API has events and user-initiated `downloads.open`, not a universal opening veto | Download bubble, automatic open, embedded viewer, OS opening |
| Chromium | **Unavailable** — upstream Chromium downloads API has no universal pre-open veto | Download manager, embedded viewer, OS opening |
| Microsoft Edge | **Unavailable** — Chromium-family API; no documented universal veto; version-specific behavior unverified | Download manager, embedded viewer, OS opening |
| Vivaldi | **Unavailable** — Chromium-family API; no documented universal veto; vendor behavior unverified | Download manager, embedded viewer, OS opening |
| Opera | **Unavailable** — Chromium-family API; no documented universal veto; vendor behavior unverified | Download manager, embedded viewer, OS opening |
| Arc | **Unavailable** — Chromium-family API; no documented universal veto; vendor behavior unverified | Download UI, embedded viewer, OS opening |
| Mozilla Firefox | **Unavailable** — documented Firefox `downloads` API can observe or invoke opening after user action, not veto all opens | Downloads panel, PDF.js, OS opening |
| Apple Safari | **Unverified; treat as unavailable** — no verified Safari Web Extensions API for strict download-opening interception | Safari inline PDF viewer, Downloads UI, Finder |

### Why common download APIs do not satisfy strict interception

- `downloads.onCreated`, `downloads.onChanged` and `downloads.onErased`
  notify the extension about download activity; notification is **not**
  an inline, cancellable, before-open decision. Even a reported `complete`
  transfer can precede native scanning. Events also do not cover PDFs
  previewed inline without a download.
- Chromium's `downloads.onDeterminingFilename` can defer **filename
  selection and completion of that download** while its suggestion is
  pending. It does **not** give an extension a general right to veto all
  browser/OS opening actions or guarantee interception of inline viewing.
  It is not a substitute for an authenticated scan gate and must not be
  held open indefinitely to simulate one.
- `downloads.open` is an **extension-initiated** operation, requiring
  separately granted permissions and a user gesture in documented Chrome
  and Firefox flows. Not calling it prevents only **that extension's**
  open request; it does not disable the browser's own menus, automatic-open
  preferences, other extensions or external file managers.
- Chromium ancestry alone is not proof of identical version-specific
  behavior in Brave, Edge, Vivaldi, Opera or Arc. Safari supports a
  WebExtension compatibility model, but undocumented or unsupported
  methods cannot be assumed to exist; no Safari-specific strict
  pre-open veto has been verified here.

### Enforcement consequence

A trusted native scanner can enforce **its own** user-requested open only
after all required ClamAV, signature freshness, current-file identity,
integrity, quarantine and selected-application checks succeed. That is
**controlled native handoff**, not browser-wide strict interception. For
the nine browsers above, PDF Magic Opener must **not** advertise
"all PDFs cannot be opened before scanning" or automatically change
download/viewer preferences. A separate, browser-specific and OS-specific
design, user consent and real installed-browser tests would be required
before claiming a stronger interception guarantee. Current shipped
background and popup remain inactive; no public-downloads API can be
treated as an enforcement guarantee just because the extension is packaged.

Supporting vendor API references (same set used for the controlled-opening
matrix below): [Chrome downloads API](https://developer.chrome.com/docs/extensions/reference/api/downloads),
[Firefox downloads API](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads),
[Firefox downloads.open](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/downloads/open),
[Edge extension API support](https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/api-support)
and [Safari extension API compatibility](https://developer.apple.com/documentation/safariservices/assessing-your-safari-web-extension-s-browser-compatibility).

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
