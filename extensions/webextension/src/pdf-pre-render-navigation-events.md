# Pre-render navigation event timeline (opener-0779)

**Scope:** identify the *candidate* browser event phases that can be observed
before some HTTP(S) PDF rendering paths. The current extension does not register
any event listeners, request permissions, intercept responses, scan, or open PDFs.

## Relevant events and timing

| Event | Relative point | Can be observed before some PDF rendering? | PDF evidence |
| --- | --- | --- | --- |
| `webNavigation.onBeforeNavigate` | Before a document navigation begins | **Potentially** | URL suffix only; not a MIME/byte verdict |
| `webRequest.onBeforeRequest` (`main_frame`) | Before network request | **Potentially** | URL suffix only; request can redirect to HTML |
| `webRequest.onBeforeRedirect` (`main_frame`) | Before a redirect occurs | **Potentially** | **None**: original URL and redirect destination do not prove the final resource |
| `webRequest.onHeadersReceived` (`main_frame`) | After response headers arrive, before corresponding response body processing | **Potentially**, where observable | `Content-Type` PDF response hint; an extensionless URL can be PDF |
| `webNavigation.onCommitted` | Navigation commits | **Not a guaranteed pre-render checkpoint** | Not a pre-response evidence source |
| `webNavigation.onDOMContentLoaded` | DOM document load | **Not** a pre-render checkpoint; optional for some documents/viewers | None |
| `webNavigation.onCompleted` | Navigation completes | **Too late** for a pre-render guarantee | None |
| `webNavigation.onErrorOccurred` | Navigation fails | **Not** a render checkpoint | None |
| `webRequest.onCompleted` | Network request completes | **Too late** for a pre-render guarantee | None |

Chrome documents the successful `webNavigation` sequence as
`onBeforeNavigate -> onCommitted -> [onDOMContentLoaded] -> onCompleted`,
with `onErrorOccurred` ending a failed navigation. Crucially, there is
**no guaranteed ordering** between `webRequest` and `webNavigation`
events, and a new navigation may supersede an earlier one.
A browser may render through its own built-in viewer, a Firefox PDF.js
document, an iframe or a site's JavaScript PDF viewer. Some PDF paths,
`blob:`, `data:`, `file:`, cached resources and internal browser viewer
pages may not expose the same events. Redirect chains can involve multiple
request/response header events, so only independently authenticated final
response evidence can identify the candidate at the final destination.

The `identifyPdfPreRenderNavigationEvent(event, details)` helper implements
this conservative event-stage classification using existing reviewed
`detectPdfNavigation` and `classifyHtmlOrPdfResponse` functions. It requires
a browser-supplied top-level tab/frame event, and a `main_frame` resource
type for `webRequest`. It exposes only immutable fixed-stage labels and
`pdfEvidence` (`url-path-hint`, `response-mime-hint`, `html-response`,
or `none`); never raw URL, headers or filenames. Unknown or forged events
fail closed. A URL/MIME hint is not proof of PDF bytes or a scanner result.

**A potentially early event is not a synchronous veto.** Even a real callback
does not guarantee it runs before the PDF viewer can process bytes, nor that
it can cancel or defer the request. Chrome MV3 generally restricts
`webRequestBlocking` to policy-installed extensions; Firefox response-body
filtering and Safari/DNR behavior are different and conditional. No
WebExtension navigation event alone provides a universal pre-render or
pre-open guarantee. Neither `downloads.onCreated` nor the eventual
download completion can ensure inline PDFs were held for scanning.

A future separately reviewed interception experiment requires explicit user
consent and browser permissions, a threat model, authentication of browser
events and native scan results, full ClamAV/signature freshness checks,
quarantine and stable file identity, as well as preservation of user-selected
PDF applications/preferences. It also requires **browser-specific live
experiments** across Chrome, Chromium, Brave, Edge, Vivaldi, Opera, Arc,
Firefox, and Safari for redirects, inline PDFs, iframe/PDF.js viewers,
cached files, and service worker/browser internal paths. This task makes
no universal timing or interception guarantee and changes no live listeners.

## Primary documentation

- [Chrome webNavigation API and event order](https://developer.chrome.com/docs/extensions/reference/api/webNavigation)
- [Chrome webRequest lifecycle and onHeadersReceived](https://developer.chrome.com/docs/extensions/reference/api/webRequest)
- [Mozilla webRequest.onHeadersReceived](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/onHeadersReceived)
- [Mozilla webNavigation API](https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webNavigation)
- [Existing browser interception feasibility study](../../../docs/browser-interception-apis.md)

Tests cover all phases, preliminary URL vs final response-MIME hints, redirects,
HTML at a PDF-suffixed URL, late-event safeguards, malformed event records,
privacy, and the unchanged inactive permission/background model. The suite is
included in WebExtensions `npm test` and has a dedicated required CI step.
