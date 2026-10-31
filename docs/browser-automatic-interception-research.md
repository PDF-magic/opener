# Research automatic PDF interception in all supported browsers (opener-0777)

**Reviewed October 30, 2026. NOT an implementation or a verified live
interception feature.** This is the per-browser follow-up to the existing
[general API research](browser-interception-apis.md) and
[pre-open download policy research](download-opening-browser-support.md).
The nine supported macOS browser identifiers are maintained by
[browser_registry.py](../browser_registry.py). The
[versioned capability matrix](browser-automatic-interception-capabilities.json)
records research confidence rather than claiming any interception is enabled.

## Browser-specific capability matrix

"Documented" means a vendor documents the API family, **not** successful
PDF interception by this project. "Conditional" is an upstream Chromium
inference or a fork vendor compatibility claim without a live test. "Policy
only" means Chrome/Edge's MV3 enterprise-policy-installed exception; do not
interpret it as permission for ordinary Chrome Web Store extensions.
"Not established" means no researched primary source confirms that API
for this browser. **None** of these paths guarantees that every PDF cannot be
opened before a mandatory native scan.

| Browser | macOS bundle ID | DNR network rules | Blocking webRequest (MV3) | Response body stream | Download events | Assessment |
| --- | --- | --- | --- | --- | --- | --- |
| Brave | com.brave.Browser | Conditional | Conditional, policy-only lineage | Not established | Conditional | Chrome MV3 extensions supported; Brave Shields, PDF viewer and precise permission/rule parity need testing |
| Google Chrome | com.google.Chrome | Documented | Policy-installed only | Not established | Documented | DNR is rule-based; no normal MV3 blocking listener or universal browser PDF open veto |
| Chromium | org.chromium.Chromium | Conditional | Conditional, policy-only lineage | Not established | Conditional | Upstream Chromium functionality depends on tested build/version and enterprise configuration |
| Microsoft Edge | com.microsoft.edgemac | Documented | Policy-installed only | Not established | Documented | Microsoft recommends DNR and retains observational webRequest; enterprise policy exception applies |
| Vivaldi | com.vivaldi.Vivaldi | Conditional | Conditional, policy-only lineage | Not established | Conditional | Chrome Web Store compatible, but Vivaldi cautions that extension behavior can differ |
| Opera | com.operasoftware.Opera | Conditional | Conditional, policy-only lineage | Not established | Conditional | Opera documents Downloads and Web Request; MV3 rule parity and PDF interception unproven |
| Arc | company.thebrowser.Browser | Conditional | Conditional, policy-only lineage | Not established | Conditional | Arc is Chromium-based and supports Chrome extensions, not proof of identical PDF request behavior |
| Mozilla Firefox | org.mozilla.firefox | Documented | Documented, with API and host grants | Documented Firefox-specific | Documented | Blocking webRequest and response stream filtering can affect eligible requests, not OS opens |
| Apple Safari | com.apple.Safari | Documented, Safari-specific | Not established | Not established | Not established | Safari DNR rules require grants and version-specific actions; native app messaging is not PDF interception |

## How the mechanisms differ

1. **Downloads:** Chrome and Firefox downloads.onCreated/onChanged can
   observe already-started transfers; this is not a synchronous veto over
   inline viewing, automatic opening, another extension, Finder or the OS.
   Chromium forks need their own installed-version checks.
2. **DNR:** DeclarativeNetRequest block/redirect rules can control matching
   network requests, not pass complete PDF bytes to ClamAV, delay all inline
   viewers, or gate cached, blob:, data:, file: and previously saved files.
   Redirects, missing .pdf suffixes, signed URLs, and extension conflicts
   make naive URL classifiers unreliable.
3. **Blocking webRequest:** Chrome MV3 restricts webRequestBlocking to
   policy-installed extensions; Microsoft's Edge MV3 documentation says
   the same. Firefox MV3 supports blocking webRequest with explicit grants,
   including matching requested resources and their initiators as applicable.
4. **Firefox response-stream filtering:** filterResponseData requires
   webRequest, webRequestBlocking and host access. Since Firefox 110, MV3
   also requires webRequestFilterResponse. The extension must close or
   disconnect streams. A separate bounded-buffer, timeout, response-body
   completeness and trusted-native scan design is necessary.
5. **Safari:** Apple documents Safari Web Extensions DNR block/allow and
   other actions, with redirect from Safari 15.4 and modifyHeaders from
   Safari 16.4, with specific host permission requirements. This is
   content/network rule support, not a generic file-opening interlock.

## Primary vendor documentation

- Brave: https://brave.com/learn/using-chrome-extensions-in-brave/
- Google Chrome: https://developer.chrome.com/docs/extensions/reference/api/declarativeNetRequest
- Chromium upstream: https://developer.chrome.com/docs/extensions/reference/api/webRequest
- Microsoft Edge: https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/api-support
- Microsoft Edge MV3: https://learn.microsoft.com/en-us/microsoft-edge/extensions/developer-guide/migrate-your-extension-from-manifest-v2-to-v3
- Vivaldi: https://help.vivaldi.com/desktop/appearance-customization/extensions/
- Opera: https://help.opera.com/en/extensions/apis/
- Opera architecture: https://help.opera.com/en/extensions/architecture-overview/
- Arc: https://arc.net/faq
- Mozilla Firefox permissions: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/manifest.json/permissions
- Firefox filterResponseData: https://developer.mozilla.org/en-US/docs/Mozilla/Add-ons/WebExtensions/API/webRequest/filterResponseData
- Safari DNR: https://developer.apple.com/documentation/safariservices/blocking-content-with-your-safari-web-extension
- Safari WWDC26: https://developer.apple.com/videos/play/wwdc2026/216/

**No OS/Finder/all-open guarantee** follows from any of these sources.
They document mechanisms, not a working scanned-PDF interception service
in the project. Network blocking must never be described as a completed
native ClamAV scan, a verified safe file, or an enforceable all-path veto.

## Decision, prerequisites and per-browser experiments

**Research only. Keep automatic interception disabled.** The shared MV3
manifest has no webRequest, DNR, broad host, debugging or downloaded-file
opening permission. Its background worker is inert. Safari's separate
nativeMessaging capability is not permission to intercept network PDF
responses. Do not silently change permissions, enable an observer, alter
browser PDF/download settings, add <all_urls>, or change user preferences.

For a future separately approved opt-in implementation, test each of the
nine browsers and its installed version in a disposable profile: actual
permissions and API shape, PDF inline and attachment, cross-origin frames,
redirect chains, signed/extensionless URLs, cache/blob/data/file sources,
auto-open and competing extensions. Verify that a rule blocks *before*
access, that timeouts/restarts/revocations fail safely, and that any native
handoff authenticates the exact PDF bytes, current file identity, ClamAV
signature freshness, quarantine, and the saved PDF app. Specifically test
Firefox response-filter buffering and disconnect behavior, Safari's
versioned rule actions and site grants, and each Chromium fork's actual
DNR and browser PDF viewer behavior. No extension-only mechanism here
has been shown to prevent OS-managed opens.

The associated CI test covers matrix-to-registry parity, source coverage
for every browser and unchanged inactive browser safety defaults. It does
**not** replace real-browser interception/security experiments.
