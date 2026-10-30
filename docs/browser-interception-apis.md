# Explore browser interception APIs for stronger PDF opening enforcement (opener-0716)

**Research status: 2026-10-30. This is a feasibility assessment, not an
implementation or guarantee of browser-wide enforcement.** The current shared
WebExtension is intentionally inactive, has no network-interception or
`downloads.open` permissions, and has an inert background worker. Safari's
separate manifest declares native messaging for its containing application,
not network interception. See the existing
[browser-opening support matrix](download-opening-browser-support.md) and
[pre-monitoring opening risk assessment](../extensions/webextension/src/download-early-open-assessment.md).

## Threat model and required guarantees

A post-download `downloads.onChanged` observer may see a completed PDF
**after** it has already become available for browser downloads UI, inline PDF
viewing, Finder, another extension, or the operating system. An event or a
clean-looking browser danger label is not a synchronous open veto. If a policy
requires stronger control, first identify whether the requirement is
**blocking particular network requests**, **preventing browser inline
rendering**, **preventing a download being materialized**, or **preventing
all local file opening**. These are different security boundaries. No
WebExtension interception API here supplies the last guarantee.

## Candidate APIs, permissions, and limits

| Mechanism | Supported or documented environment | Possible enforcement | Why it is insufficient by itself |
| --- | --- | --- | --- |
| `downloads.onCreated`, `downloads.onChanged`, `downloads.search` | Chrome/Chromium family and Firefox downloads APIs; individual forks need live verification | Observe transfer lifecycle and correlate a completed download to a native scan | **Observational**, not an interlock over downloads UI, inline PDF viewing, Finder, auto-open or other applications; callbacks can arrive after file availability |
| `downloads.onDeterminingFilename` | Chrome documents an asynchronous filename suggestion before a download completes; browser-specific behavior must be tested | Suggest a relative download filename and coordinate naming | Not an antivirus scan callback or a universal completion/open veto; another extension can win the filename suggestion, and the API must call `suggest` rather than wait indefinitely |
| `downloads.pause`, `downloads.cancel` | Chrome/Chromium downloads API; verify fork parity and Firefox separately | Control the **specific active download** when the extension receives the event early enough | A race remains; it does not revoke bytes or a file already available to the user, and cancelling a dangerous download is not permission to bypass browser warnings |
| `declarativeNetRequest` (DNR) `block`/`redirect` | Chrome MV3, Firefox WebExtensions and Safari Web Extensions document declarative network filtering; supported actions/permissions vary | **Before or during network requests**, apply declarative conditions to block or redirect selected URL/resource requests without synchronous extension JavaScript | Static or dynamic rules do not obtain a complete native ClamAV verdict on the final local PDF; rules cannot guarantee capture of inline/cache/local/blob/data/file URLs or independent local opening, and resource-type/MIME/redirect coverage needs browser-specific tests |
| `webRequest` observation | Chrome MV3 with `webRequest` and host access; Firefox with matching host permissions | Observe eligible web request timing, headers and metadata | Nonblocking observation does not stop a request or a browser/OS file open; visibility depends on initiator, host permissions and browser restrictions |
| Blocking `webRequest.onBeforeRequest` or `onHeadersReceived` | **Firefox** documents `webRequestBlocking` in MV3 and allows blocking, cancel/redirect (including Promise-based `onBeforeRequest` decisions). **Chrome MV3** restricts `webRequestBlocking` to policy-installed extensions | Potentially interpose on **eligible network requests** earlier than download completion | Not a universal file-open hook; host access and granted permissions are required, unobserved browser-internal/local operations remain possible, and an async native scan cannot assume it can indefinitely suspend requests |
| `webRequest.filterResponseData` | **Firefox-specific** documented response-stream filtering requiring `webRequest`, `webRequestBlocking` and host permission | Interpose on a matching network response stream, potentially buffering it for a separately trusted scanner | Full response buffering, compressed bodies, resource/caching contexts, memory/time limits, browser stream failure paths and user privacy require independent engineering; not a cross-browser API or a guarantee against other file opens |
| Browser enterprise policy / managed extension | Browser- and administrator-specific managed deployments; Chrome documents policy-installed blocking `webRequest` exception | Potentially restrict selected download/open behaviors under **separately configured** administrative controls | No common permission-free WebExtension hook; cannot claim this project controls unmanaged devices, other applications or all local file access |
| Native macOS verified handoff | Existing PDF Magic Opener native `scan-and-open.py` pipeline; independently authenticated extension-to-native coordinator still required for browser downloads | Gate **PDF Magic Opener's own opening commands** after a complete clean ClamAV scan, fresh signatures, canonical identity, integrity, quarantine retention and verified selected-app handoff | Cannot prevent the browser's own viewer/auto-open, Finder, other apps or unrelated download initiation; not presently wired into live browser interception |

### Important browser-family distinctions

- **Chrome and Chromium MV3:** the documented general-purpose blocking
  `webRequestBlocking` exception is for **policy-installed extensions**;
  normal MV3 extensions should assess DNR. DNR operates on network
  requests and evaluates rule conditions, not native scan results. Neither
  extension-originated `downloads.open` nor a DNR block means the
  extension has acquired control over all PDF opening paths.
- **Brave, Edge, Vivaldi, Opera and Arc:** treat Chrome-compatible interfaces
  as **conditional**, not a tested support guarantee. Review each installed
  browser/version's feature flags, enterprise policies, extension signing,
  permissions and user download/PDF viewer settings independently.
- **Firefox:** `webRequestBlocking` remains documented for MV3 and Firefox
  documents `filterResponseData` for response-stream control. These APIs
  may support a **separate experimental Firefox-specific** mediation design,
  but stream ownership, async timeout, native scanner admission and
  fail-closed cancellation must be tested before enabling it. Do not
  silently request broad host access to prototype this.
- **Safari:** Apple documents **declarativeNetRequest** content blocking for
  Safari Web Extensions, with Safari-specific permitted action types,
  permissions and version constraints. The presence of an extension's
  native app messaging channel does **not** establish a synchronous
  downloaded-PDF opening hook. Never assume parity with Firefox's
  stream-filtering APIs or Chrome's downloaded-file open API.

## Decision: keep current behavior, prototype only behind explicit review

1. **Do not enable interception in this checklist task.** Keep the shared
   `manifest.json`, the Safari manifest, native host, popup and inactive
   background unchanged. There is no deployed authenticated native scanner
   coordinator to hold and reconcile an intercepted request. Do not expand
   to `<all_urls>`, `webRequestBlocking`, `declarativeNetRequest` or
   `downloads.open` without a separate permissions/privacy design and
   explicit user consent. No change may disable a browser's built-in
   dangerous-download checks or silently modify the user's PDF preferences.
2. **Preferred supported flow today:** keep the native scanner's own
   verified file-opening gate. The opt-in
   [Open After Scanning action](../extensions/webextension/src/download-open-after-scanning.md)
   expresses user intent only; `accepted` does not authorize opening.
   Preserve verified download identity, quarantine, ClamAV signature
   freshness, complete clean verdict, and the user's selected application
   at final native handoff.
3. **For a future stronger browser policy:** prototype DNR `block` rules
   against **explicitly opted-in sites or request classes** in disposable
   profiles, or a Firefox-specific blocking/stream-filter experiment.
   Neither may claim native-scanner-based all-path interception without
   proving the full byte and opening lifecycle. If policy requires
   **all local opening paths**, evaluate OS-managed access restrictions
   separately, not just browser extension APIs. Release behavior must
   remain fail-closed for unavailable APIs, missing permissions,
   incomplete scans, disconnects, timeouts, canceled jobs, and changed
   files; never replay a scan automatically after an unknown outcome.

For browsers without a reliable universal pre-open veto, the separately
opted-in [managed download, scan and open action](../extensions/webextension/src/download-managed-open.md)
provides a **future trusted-native route for the user's explicit request only**.
Its native coordinator is not deployed, and it does not control browser-owned
opening paths, alter download settings, or authorize opening on a queue receipt.

## Experiments required before promising stronger enforcement

For each supported browser and installed version, use a disposable profile
and independently verify the following. A documentation/unit-test pass is
**not** an end-to-end browser security claim.

- Permission prompts and actual API availability, including MV3 versus
  policy-installed restrictions; `webRequestBlocking` and
  `declarativeNetRequest` are **not interchangeable**.
- Inline PDF viewer versus attachment download; redirects and dynamically
  generated PDFs; `blob:`, `data:`, `file:` and cached resources;
  browser auto-open, downloads shelf, private profiles and other extensions.
- Exactly when a request becomes observable/blockable relative to transfer,
  filename selection, file materialization and user opening; verify failure
  behavior on worker suspension, native disconnection, download cancellation
  and denied/revoked host permissions.
- DNR allow/block priority, competing extensions and update races; Firefox
  response-stream byte completeness, upper bounds, stall/cancellation and
  resource exhaustion; Safari's supported rule conditions and version limits.
- Trusted native authentication, request-to-download ID correlation,
  independently verified canonical identity, ClamAV signature freshness,
  complete scan verdict, preserved quarantine and **only the native
  verified selected application** as the eventual opener.
- Test that an OS/Finder open or another program does **not** become falsely
  represented as blocked. Any future user-facing claim must describe the
  *specific browser requests actually controlled*, not “all PDFs are
  scanned before they can be opened.”

## Primary API references

- [Google Chrome: webRequest and MV3 blocking limitation](https://developer.chrome.com/docs/extensions/reference/api/webRequest)
- [Google Chrome: declarativeNetRequest](https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest)
- [Google Chrome: downloads and onDeterminingFilename](https://developer.chrome.com/docs/extensions/reference/api/downloads)
- [Mozilla: intercept HTTP requests](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/Intercept_HTTP_requests)
- [Mozilla: blocking onBeforeRequest](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/onBeforeRequest)
- [Mozilla: filterResponseData](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/filterResponseData)
- [Mozilla: MV3 blocking versus Chrome](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/onAuthRequired)
- [Apple: blocking content with a Safari Web Extension](https://developer.apple.com/documentation/safariservices/blocking-content-with-your-safari-web-extension)

These vendor documents establish **available mechanisms**, not their
deployment in PDF Magic Opener or guarantees of scanner interposition.
