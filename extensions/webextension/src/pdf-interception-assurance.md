# Distinguish enforcement from best-effort monitoring (opener-0798)

The browser extension currently **does not enforce automatic scan-before-render**
for any supported browser. A notification about a PDF URL or download is **not**
evidence that a PDF was blocked, captured in full, scanned with ClamAV, or
prevented from being viewed.

The passive, read-only
[pdf-interception-assurance.js](pdf-interception-assurance.js)
provides a stable, user-facing classification of a reported browser event
without requiring extra browser permissions or activating interception:

| Classification | Meaning | Display |
| --- | --- | --- |
| Inactive | No event or working interception established | "Automatic PDF interception inactive" |
| Best-effort monitoring | A browser navigation, header, download or rule-match notification may reveal PDF activity, but may arrive too late or be skipped | "Best-effort monitoring — PDF opening is not blocked" |
| Unverified request-blocking candidate | A reported main-request preflight point might *conditionally* block a matching network request on browsers whose API is documented; effective installed grants are unverified | "Unverified request-blocking candidate — not scan-before-open enforcement" |

In particular, \`declarativeNetRequest.onRuleMatchedDebug\` is an
**observation of a matching rule**, not proof that its action was a block;
\`webRequest.onBeforeRequest\` is a candidate before-request point, not proof
that a synchronous veto occurred. Firefox's blocking listener needs effective
host/API grants, while normal Chrome and Edge MV3 do not provide the general
blocking listener except for the documented enterprise policy-installed case.
Safari has no established equivalent blocking listener.

An enforceable **scan-before-render** path must demonstrably prevent rendering
of the exact current PDF until complete response bytes are safely captured,
verified by trusted native ClamAV scanning, and held or blocked on all failure
paths. The installed browser/version, opt-in, effective permission and
request-to-tab identity must be proven; scanner readiness, signature freshness,
quarantine, bounded timeouts and safe disconnection/restart are necessary too.
A request blocker alone affects only **matching network requests**, not cached
or inline responses, data/blob/file URLs, browser viewer internals, other
extensions or operating-system opens. Neither event reports nor a guessed
scan verdict can authorize an open.

The classifier's \`activeMonitoringVerified\`,
\`effectiveRequestBlockingVerified\`, \`nativeScanBeforeRenderVerified\`,
\`allPdfOpeningPathsBlocked\`, \`mayClaimEnforcedProtection\`, \`authorizesScan\`
and \`authorizesOpen\` fields are always false. Its input is a kind of
*reported* event, **not an authenticated observation**. Therefore a label
must never be shown as proof of live protection without a separately reviewed
trusted coordinator. A future coordinator must establish enforcement using
verified evidence rather than promoting an observed event or opted-in setting.

No native scan, browser listener, browser permission, on-disk setting or user
preference is changed. The existing scanner safety gates and chosen PDF
application remain authoritative. The source is included in the ordinary
WebExtensions \`npm test\` CI wildcard; the regression suite tests all nine
registered browsers, conditional API distinctions, falsely claimed blocking,
unknown and hostile data, immutable fail-closed results and unchanged manifests.
