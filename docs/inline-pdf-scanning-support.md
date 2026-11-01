# Inline PDF scanning support by browser (opener-1124)

**Current status (November 1, 2026): PDF Magic Opener does not actively scan
PDFs before they render inline in any of its nine registered browsers.**
This is a statement about the **installed PDF Magic Opener integration**, not
about whether those browsers can display a PDF, whether a vendor documents
network interception APIs, or whether a future integration is possible.

Here, **inline PDF scanning** means reliably holding a PDF displayed *inside*
a browser tab, built-in PDF viewer, PDF.js page, `iframe`, `object` or
`embed` **before rendering** until the complete bytes have passed an
authenticated native ClamAV scan and the scan result and file/response identity
have been verified. Download observation, a filename hint, a viewer smoke test,
a permission declaration, or a browser's own security checks do **not** prove
that PDF Magic Opener has performed this scan.

## Browser-by-browser support

| Browser | macOS bundle ID | Browser inline PDF display | PDF Magic inline scan | Current limitation |
| --- | --- | --- | --- | --- |
| Brave | `com.brave.Browser` | Chromium-family viewer; settings-dependent | **No — inactive** | Chromium MV3 rules, Shields and viewer behavior do not establish a native scan hold. |
| Google Chrome | `com.google.Chrome` | Built-in PDF viewer when enabled | **No — inactive** | Declarative rules do not await ClamAV; blocking `webRequest` is policy-installed-only in MV3. |
| Chromium | `org.chromium.Chromium` | Chromium-family viewer; build-dependent | **No — inactive** | Build-specific viewer and network-rule behavior are not validated as a scanner interlock. |
| Microsoft Edge | `com.microsoft.edgemac` | Edge PDF viewer when enabled | **No — inactive** | MV3 rules cannot wait on native scanning; blocking `webRequest` is policy-installed-only. |
| Vivaldi | `com.vivaldi.Vivaldi` | Chromium-family viewer; settings-dependent | **No — inactive** | Fork-specific permissions, response handling and viewer behavior are unverified. |
| Opera | `com.operasoftware.Opera` | Chromium-family viewer; settings-dependent | **No — inactive** | Browser API availability is not proof of a reliable pre-render scan hold. |
| Arc | `company.thebrowser.Browser` | Chromium-family viewer; settings-dependent | **No — inactive** | Chrome extension compatibility does not prove control of Arc's inline viewer. |
| Mozilla Firefox | `org.mozilla.firefox` | Built-in PDF.js when enabled | **No — inactive** | `webRequest.filterResponseData` is documented with grants, but no trusted, complete native scan-and-release integration exists. |
| Apple Safari | `com.apple.Safari` | Safari's inline PDF display when enabled | **No — inactive** | Safari network rules and native messaging do not establish a scanner-controlled byte hold. |

The identifiers match the [supported browser registry](../browser_registry.py).
The [research capability data](browser-automatic-interception-capabilities.json)
and the [runtime's disabled reliability policy](../extensions/webextension/src/automatic-interception-capability-matrix.js)
are the implementation evidence for the **inactive** statuses. All nine rows
require separate live, permission-aware browser and scanner verification before
any status could be upgraded. Firefox's potential response-stream interception
is **not** deployed. The Chrome and Edge enterprise-policy exception is **not**
available to an ordinary installed extension.

## What the current product can scan

PDF Magic Opener's **native macOS path** can scan a *locally available* PDF
when the user opens it through the PDF Magic Opener handler (for example, in
Finder with **Open With → PDF Magic Opener**, or by making it the default PDF
handler). A clean verdict must still satisfy signature freshness, file
identity/integrity, quarantine preservation, and verified application handoff.
The chosen browser may then be the **post-scan destination**, but this does
not mean PDF Magic Opener has scanned PDFs that the browser independently
loads or displays inline.

If a browser displays a PDF in its own tab, **do not treat that view as scanned
by PDF Magic Opener**. To use the native gate for a PDF acquired in a browser,
save it as a local PDF and explicitly open that file with PDF Magic Opener;
do not assume automatic downloads, inline previews, browser cache entries,
or browser-managed opening trigger the native scan.

## Limits and evidence

Browser-owned built-in viewers, site-hosted PDF.js, frames and embeds, cached
responses, redirects, and `blob:`, `data:` and `file:` URLs do not pass
through a demonstrated universal pre-render scan gate. A viewer that supports
inline display is **not** the same thing as a browser that supports PDF Magic
inline scanning. The shared WebExtension's background remains inactive; this
guide does not request permissions, enable interception, alter PDF handling
preferences, or relax the scanner's fail-closed behavior.

For detailed route classifications and vendor-API distinctions, see
[unsupported PDF entry routes](browser-unsupported-routes.md),
[automatic interception research](browser-automatic-interception-research.md),
[browser viewer differences](browser-pdf-viewers.md), and
[browser API limits](browser-interception-apis.md). The real Chrome, Firefox
and Safari viewer smoke tests verify **viewing**, not native scanning or
scan-before-render authorization.
