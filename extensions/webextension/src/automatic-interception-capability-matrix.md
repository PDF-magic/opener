# Optional automatic PDF interception — deployment capability matrix (opener-0778)

**Status: inactive for all browsers (2026-10-30).** This is a conservative
capability and permission-planning matrix, **not** a claim that PDFs can be
intercepted, downloaded or opened safely by an installed extension. No browser
has a deployed PDF Magic Opener interception route.

The machine-readable `src/automatic-interception-capability-matrix.js` lists
all nine browser IDs in the canonical [browser registry](../../../browser_registry.py).
Unlike the separate static *vendor API research* being prepared in
[opener-0777](https://github.com/PDF-magic/opener/pull/534), this is the
**current project's deployment decision** and a passive, tested observation
of API *shapes* for an explicitly selected browser. Its only effective
interception status is **inactive**.

## Browser capability matrix

| Browser | Family | Declarative network rules | Blocking webRequest | Response body interception | Download events | PDF Magic Opener automatic interception |
| --- | --- | --- | --- | --- | --- | --- |
| Brave | Chromium | Conditional; verify fork/version | Conditional enterprise-policy exception; verify | Unverified | Conditional | **Inactive** |
| Google Chrome | Chromium | Documented DNR | Policy-installed extension only in MV3 | Unverified | Documented | **Inactive** |
| Chromium | Chromium | Conditional; verify build/version | Conditional enterprise-policy exception | Unverified | Conditional | **Inactive** |
| Microsoft Edge | Chromium | Documented DNR | Policy-installed extension only in MV3 | Unverified | Documented | **Inactive** |
| Vivaldi | Chromium | Conditional; verify fork/version | Conditional enterprise-policy exception | Unverified | Conditional | **Inactive** |
| Opera | Chromium | Conditional; verify fork/version | Conditional enterprise-policy exception | Unverified | Conditional | **Inactive** |
| Arc | Chromium | Conditional; verify fork/version | Conditional enterprise-policy exception | Unverified | Conditional | **Inactive** |
| Mozilla Firefox | Gecko | Documented DNR | Documented, with grants | Firefox-specific filterResponseData with grants | Documented | **Inactive** |
| Apple Safari | WebKit | Documented Safari-specific rules | Unverified | Unverified | Unverified | **Inactive** |

**Documented** identifies a vendor-supported API, not an authorized extension
or a tested PDF interception path. **Conditional** means a Chromium-derived
or version-dependent expectation requiring installation and permission tests.
**Unverified** means do not assume support. Safari's containing-app
`nativeMessaging` permission does **not** enable downloaded-PDF interception.
Neither download-event observation nor declarative network filtering is a
universal synchronous veto on every browser viewer and operating-system open.

## Effective status and required gates

`assessAutomaticPdfInterception(browserId, suppliedApi)` can inspect only
*own data-property* API shapes for downloads events, DNR methods, blocking
webRequest events and Firefox response filtering. The caller selects the
browser explicitly; it never uses user-agent sniffing. API presence alone
cannot establish consent or any effective host, browser or native permission.

The returned immutable report always sets
`automaticInterceptionEnabled:false`, `permissionVerified:false`,
`nativeScanInterlockVerified:false` and `allPdfOpeningBlocked:false`.
Unknown browser IDs fail closed. Even a full mocked API surface does not
change these flags. The installed shared Manifest V3 extension has zero
mandatory and host permissions, only optional `downloads`, and an **inert
background worker**. Safari separately declares `nativeMessaging`, not
network interception. No manifest, UI, preference, downloader, native host
or browser permission is changed by this task.

A later feature requires all of the following in a separately reviewed
opt-in integration: per-browser/version disposable-profile testing; genuine
user consent, effective optional site/host/network permissions and revocation;
coverage decisions for navigations, inline viewers, attachments, redirects,
signed/extensionless links, blob/data/file/cache and other extensions; bounded
timeouts and worker restart behavior; browser dangerous-download warnings;
complete PDF bytes, trustworthy identity, native ClamAV signature freshness,
full clean scan and quarantine; and the user's selected verified PDF
application. A partial network block does not prove **all local PDFs**
cannot be opened before scanning; Finder and other applications remain
outside the WebExtension's control. A strict pre-open guarantee is unavailable.

For vendor mechanisms and source links, consult the existing primary-source
[interception feasibility assessment](../../../docs/browser-interception-apis.md)
and [browser download-opening support](../../../docs/download-opening-browser-support.md).
The separate opener-0777 research PR provides browser-by-browser vendor
source confidence, while opener-0778 specifies **project-effective** flags
that must not be promoted to enabled merely by those research findings.

CI: `tests/automatic-interception-capability-matrix.test.mjs` is included
in the existing WebExtensions `npm test` glob, and independently checks the
nine IDs against `browser_registry.py`, API-shape safety, inactive manifests,
absence of interception listeners and no scan/open authorization.
