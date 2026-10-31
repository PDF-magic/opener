# Enforceable PDF interception points by browser (opener-0781)

**Reviewed October 30, 2026. Finding: no verified scan-before-render interception point exists in the currently shipped PDF Magic Opener browser extensions.** This does not mean that browsers cannot block matching network requests. Their limited network controls must not be confused with a complete native PDF scan or a veto against operating-system opening.

This decision assessment reuses the existing project deployment matrix in [automatic-interception-capability-matrix.js](automatic-interception-capability-matrix.js) and vendor research confidence in [browser-automatic-interception-capabilities.json](../../../docs/browser-automatic-interception-capabilities.json). The immutable [pdf-interception-point-assessment.js](pdf-interception-point-assessment.js) exposes the verdict for each registered browser.

## What would constitute an enforceable point?

A **matching network-request veto** can block selected HTTP(S) requests before a response arrives. DeclarativeNetRequest (DNR) requires matching rule conditions, effective site permission and browser version support. DNR rules cannot wait asynchronously for a complete native ClamAV verdict; at the before-request stage the URL may not identify the response as a PDF.

A **blocking request listener** can cancel a matching request before download or rendering in browsers that allow it. General-purpose blocking webRequest is not available to normal Chrome/Edge Manifest V3 extensions; there is a documented enterprise policy-installed exception. Firefox documents blocking webRequest with the applicable API and host grants. Chromium-derived forks require per-version verification rather than assuming Chrome parity.

A **response stream filter** offers a possible Firefox-specific way to capture complete bytes before releasing a matching response, but that would require webRequest, webRequestBlocking and the additional webRequestFilterResponse grant in applicable Firefox MV3 versions. The implementation must enforce byte completeness, bounded buffering, signature freshness, trusted native scanner handoff and fail-closed cancellation on worker or native disconnection. That integration is **not implemented**.

Download lifecycle events are observational, not synchronous browser viewer or operating-system file-opening vetoes.

## Per-browser decision

| Browser | Earliest candidate point before receiving a matching network response | Blocking listener / response-body options | Enforceable native scan before render today? |
| --- | --- | --- | --- |
| Brave | Conditional Chromium DNR rule with installed-version and site permission review | Conditional policy-installed blocking listener; response body unverified | **No** |
| Google Chrome | Documented DNR request rule with matching conditions and site permission | Enterprise policy-installed blocking listener only in MV3; response body unverified | **No** |
| Chromium | Conditional DNR depending on build/version and site permission | Conditional enterprise policy exception; response body unverified | **No** |
| Microsoft Edge | Documented DNR request rule with matching conditions and site permission | Enterprise policy-installed blocking listener only in MV3; response body unverified | **No** |
| Vivaldi | Conditional Chromium DNR with version/site verification | Conditional enterprise policy exception; response body unverified | **No** |
| Opera | Conditional Chromium DNR with version/site verification | Conditional enterprise policy exception; response body unverified | **No** |
| Arc | Conditional Chromium DNR with version/site verification | Conditional enterprise policy exception; response body unverified | **No** |
| Mozilla Firefox | Documented DNR rule with site permission | Documented blocking webRequest with grants; Firefox-only response filtering with extra grants | **No** |
| Apple Safari | Documented Safari-specific DNR with browser-version and site permission limits | Generic blocking webRequest and response body filter not established | **No** |

These are candidate network interception mechanisms, not a guarantee that the particular installed browser exposes or permits them. **Matching network requests only** is the maximum potential DNR blocking scope, and a DNR block is not a native scan result. Firefox response filtering could support a separately verified per-response gate, but that gate is absent. No row asserts PDF identification before render, a verified full response, a trusted ClamAV interlock, or browser-wide open prevention.

## Uncontrolled paths and safety gates

Even a functional request veto cannot guarantee interception of unmatched or redirected requests, inline or cached rendering, blob/data/file URLs, browser automatic opening or other extensions, Finder or other operating-system applications. It cannot guarantee all PDFs are inaccessible before native scanning.

A future explicitly opted-in implementation needs browser/version testing in disposable profiles, true user consent, revocable and scoped site permission, matching request timing verification, complete response content and file identity, bounded resource usage and timeouts, safe service worker restart/disconnection handling, ClamAV signature freshness, a complete clean verdict, quarantine and the user's selected PDF application. Do not disable browser dangerous-download checks or silently alter user preferences.

Currently the shared extension has no host or interception permission and its background is inert; Safari's nativeMessaging declaration is not a network interceptor. Automatic interception is disabled for every browser. This assessment performs no navigation, interception, download, scan, native messaging or browser API call.

The associated CI test in tests/pdf-interception-point-assessment.test.mjs is discovered by the existing WebExtensions npm test wildcard. It checks all nine registry entries, parity with the previously merged vendor research, the Chromium policy exception, Firefox and Safari distinctions, fail-closed immutable results and unchanged browser/scanner safety defaults. Live browser tests remain a prerequisite for any stronger enforcement claim.
