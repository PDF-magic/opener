# When automatic PDF interception cannot be guaranteed (opener-1125)

**Current status (November 1, 2026): automatic PDF interception is inactive in all nine supported browsers.** PDF Magic Opener cannot guarantee that a browser's PDF is held for a complete native ClamAV scan *before* the browser renders, downloads, or opens it. This is a limitation of **automatic browser interception**, not of the separately invoked macOS PDF Magic Opener native scan-and-open handler.

A **guaranteed interception** would require an effective, permitted pre-render/pre-open veto over the exact PDF bytes, an authenticated native scanner, a complete and fresh clean result, and verified release of **those same bytes** to the selected destination. Observing a URL, MIME type, tab navigation, download event, DNR rule match, installed extension, or saved opt-in does not establish any such guarantee. The browser or another application may still open a PDF outside PDF Magic Opener's control.

## Entry paths that cannot be guaranteed

These are the ten canonical path identifiers in the [disabled reliability policy](../extensions/webextension/src/automatic-interception-capability-matrix.js). All remain inactive; a path classified as **unverified** is **not** a supported interception path.

| PDF route | Why automatic interception is not guaranteed |
| --- | --- |
| `network-main-frame` | An early browser request event may identify a candidate, but does not hold final response bytes for an authenticated native scan. |
| `inline-browser-viewer` | Browser-owned PDF viewers can render independently of extension scanning. |
| `embedded-pdf` | PDFs in frames, objects, and embeds may render without a top-level interception gate. |
| `pdfjs-page` | Built-in or site-hosted PDF.js can load PDFs from viewer-managed or script-controlled resources. |
| `redirected-response` | Redirects, changed response identities, misleading MIME types and suffixless URLs can evade a preliminary match. |
| `blob-url` | A page-generated `blob:` PDF may not generate a separately interceptable HTTP response. |
| `data-url` | Inline `data:` PDF bytes do not require a browser network request. |
| `file-url` | Local `file:` URLs, including files opened from Finder, do not require a browser request. |
| `cached-pdf` | Cached resources, service workers and browser-internal fetches may not generate the assumed network event. |
| `attachment-download` | A download can reach browser download UI, automatic-open handlers, Finder or another app without an extension-controlled open veto. |

The [full unsupported-route register](browser-unsupported-routes.md) also covers cross-origin frames, private/authenticated endpoints, other extensions, custom viewers, interrupted or oversized transfers, and unrecognized routes. It is a record of known limitations, **not an exhaustive inventory of every way a PDF can be opened**.

## Browser and deployment conditions

| Browser IDs | Why a browser API is insufficient |
| --- | --- |
| Chromium family: `brave`, `chrome`, `chromium`, `edge`, `vivaldi`, `opera`, `arc` | Manifest V3 declarativeNetRequest (DNR) can block *matching requests*, but cannot await a native ClamAV verdict. Chrome/Edge blocking `webRequest` in MV3 is available only to policy-installed extensions, not ordinary installations; fork-specific viewer, version and permission behavior remains conditional or unverified. |
| Firefox: `firefox` | Documented blocking `webRequest` and `filterResponseData` require effective host/API grants, byte buffering, timeouts, and a separately implemented authenticated native scan-and-release interlock. None is deployed. |
| Safari: `safari` | Safari's supported network rules and native messaging vary by version and permission; they do not supply a proven universal native scan-before-render hold. |

Even where an interception API might be suitable for **a specific network response**, a guarantee fails if the extension is missing, not running, suspended or restarted; permissions or site access are denied or revoked; a browser version/viewer changes; redirects or caching escape the hook; bytes are incomplete or altered; an authenticated native bridge is unavailable; the scanner times out, detects a threat, or returns an inconclusive result; or the file is opened independently through the browser or operating system.

**Monitoring is not enforcement.** A download notification, navigation observation, successful PDF viewer test, or opted-in preference must not be displayed as an active gate. Neither a browser-side rule nor PDF Magic Opener can promise to block *every* PDF opening across the operating system. The [effective status](automatic-pdf-interception-status.md) stays **Inactive**, including after an opt-in.

## Safe action today

To scan a PDF acquired in a browser, **save it locally and explicitly open the saved file with PDF Magic Opener** (for example, Finder → Open With → PDF Magic Opener, or the separately configured macOS default PDF handler). The native handler must enforce a complete clean ClamAV scan with fresh signatures, stable file identity/integrity, quarantine retention, and a verified selected application before *its own* handoff. A failure, missing result or changed file blocks **PDF Magic Opener's** opening operation; it does not retroactively block browser views or other apps. Do not assume that merely downloading, previewing, or opening a PDF inside a browser invoked this handler.

Do not weaken browser dangerous-download warnings, request broad grants, change browser or operating-system PDF defaults, disable quarantine, or overwrite the user's existing custom PDF destination to compensate for these gaps.

## Conditions for a future guarantee claim

A future, separately reviewed integration would need to prove, **per browser, version, installation and relevant route**, effective consent/permissions, a synchronous pre-render/pre-open hold, identity-preserving transfer of the complete bounded PDF bytes, authenticated scanner results with freshness and integrity checks, safe release to the chosen destination, and fail-closed behavior for cancellations, timeouts, restarts, permission revocation, disconnects and bypass attempts. It must report unsupported paths honestly rather than silently falling back to unscanned opening. Tests must include actual browser and native-scanner integration; static API research or a mocked viewer test cannot establish a deployment-wide guarantee.

See [inline PDF scanning by browser](inline-pdf-scanning-support.md), [browser API research](browser-interception-apis.md), [automatic interception option](automatic-pdf-interception-option.md), and the [inactive reliability contract](../extensions/webextension/src/automatic-interception-reliability.md). This guide does **not** enable automatic interception or change scanner policy or user preferences.
