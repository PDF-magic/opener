# Browser PDF viewer differences

PDF Magic Opener **scans and verifies a local PDF before handing it to the
selected macOS application**. It does not render PDFs, supply a common PDF
viewer, or replace the chosen browser's settings. Reading, filling forms,
annotating, printing, and saving are controlled by the destination application.

For **download-opening enforcement and per-browser API limits** (as distinct
from PDF viewer features), see the [controlled opening support matrix](download-opening-browser-support.md).
This documents user-gesture-gated browser APIs versus verified native handoff;
no browser integration is currently active.

## Compare browsers and viewer families

| Browser | macOS bundle identifier | PDF viewer and practical differences |
| --- | --- | --- |
| Brave (default) | `com.brave.Browser` | Chromium-derived viewer, subject to Brave's own PDF preferences; the opener's default has no extra editing privileges. |
| Google Chrome | `com.google.Chrome` | Chrome's PDF viewer documents search, forms, annotations, drawing, and on-device OCR for scanned PDFs; feature availability varies with Chrome versions and settings. |
| Chromium | `org.chromium.Chromium` | Open-source Chromium-family viewer; do not presume that every Google Chrome-only tool is present. |
| Microsoft Edge | `com.microsoft.edgemac` | Chromium-derived viewer with Edge-specific PDF controls and preferences; the toolbar need not match Chrome's. |
| Vivaldi | `com.vivaldi.Vivaldi` | Chromium-derived viewer, with PDF handling and download settings set by Vivaldi. |
| Opera | `com.operasoftware.Opera` | Chromium-derived viewer; viewer UI and feature rollout can differ from Chrome. |
| Arc | `company.thebrowser.Browser` | Chromium-derived PDF rendering presented in Arc's browser UI and navigation model. |
| Mozilla Firefox | `org.mozilla.firefox` | Built-in **PDF.js** reader rather than Chromium's viewer; supports forms, text/drawing annotations, highlights, and visible signature marks. |
| Apple Safari | `com.apple.Safari` | PDF display in Safari's macOS interface; **Preview** is a separate app for more extensive Markup and page rearrangement. |

The canonical, machine-readable [supported browser registry](../browser_registry.py)
keeps these bundle identifiers consistent across the launcher and its tests.
It is a catalog, not an installation check or an allowlist; verified custom
applications remain configurable.

These identifiers are **installed application bundle IDs**, not commands or
promises that every browser is supported on every Mac. Chromium-derived
browsers share a lineage, but their viewers are **not identical**: feature
availability, policies, menus, and download defaults may diverge.

## What changes when you switch PDF viewers?

- **Navigation and display:** Search, zoom, page fitting, outlines, printing,
  keyboard shortcuts, and rotate controls may be in different menus.
- **Forms, annotations, and signatures:** Firefox PDF.js documents form
  filling, highlights, drawing, and signature annotations. Chrome documents
  form filling, highlighting, drawing, and signing. Other Chromium-family
  browsers may expose a different subset. A visible signature annotation
  is not necessarily a cryptographically verified digital signature.
- **Image-only/scanned PDFs:** Chrome documents on-device OCR making scanned
  text searchable. Do **not** assume equivalent OCR in Chromium, Brave, Edge,
  Vivaldi, Opera, Arc, Firefox, or Safari; test the installed viewer.
- **Open in tab or download:** Each browser has its own PDF-viewing, download,
  and sometimes administrator-controlled preferences. Choosing that browser
  in the opener does not override those preferences. A successful application
  handoff does not guarantee an in-tab view.
- **Save behavior and privacy:** Browser annotations and saving are managed
  by the viewer. PDF Magic Opener does not change PDF contents or upload them.
  Browser-specific cloud or synchronization functions have their own settings.

## What stays the same in PDF Magic Opener?

See [PDF target application](../README.md#pdf-target-application) for configuring
the destination. Brave remains the fallback when no application setting exists,
and installing updates does not overwrite an existing user selection.

The **ClamAV verdict, file-integrity, quarantine, and local-file-availability
gates** apply regardless of browser. The
[PDF target verifier](../verify-pdf-target.swift) requires the selected
application to be registered for PDF opening or satisfy a **specific verified
exception**. Some browsers display PDFs without macOS PDF-handler registration,
but a built-in viewer alone cannot bypass verification. The
[native launcher](../launch-scanned-file.swift) additionally checks the
installed application's identity and executable. Failed verification must
stop opening, **not fall back** to an unchecked handler or invoke the opener
recursively.

If the scan succeeds but the document does not display, confirm that the
selected browser is installed, passes PDF capability verification, and has
its own PDF viewer enabled. Test searchable, image-only, fillable, and
annotated sample PDFs before relying on any viewer-specific feature. Apple's
separate Preview app may be better suited to editing or rearranging pages.

## Chrome's built-in PDF viewer: automated browser check (opener-0800)

The CI **Chrome package smoke test** now also launches Google's Chrome for
Testing (stable) in a *separate*, disposable headless profile with no production
extension loaded. It serves a generated, valid, one-page PDF from a temporary
`127.0.0.1` HTTP server and performs actual top-level browser navigations to
both a `.pdf` path and an extensionless URL with `Content-Type:
application/pdf` and `Content-Disposition: inline`.

The test asserts that Chrome requests the locally served PDF, keeps the
original URL as the main-frame navigation, and exposes **actual PDF viewer
evidence**: Chrome's built-in PDF extension frame/target or an embedded PDF
plugin in the document/shadow DOM. A successful HTTP response, an ordinary
webpage, a download, or a network error cannot pass merely by returning
PDF-like metadata. The CI job fails if Chrome cannot open the document in its
built-in viewer. See
[`test-chrome-pdf-viewer.mjs`](../extensions/webextension/scripts/test-chrome-pdf-viewer.mjs)
and its [regression tests](../extensions/webextension/tests/chrome-pdf-viewer.test.mjs).

This verifies Chrome for Testing's built-in **viewing**, not that PDF Magic
Opener can block the browser's own rendering, scan native bytes beforehand,
intercept all sources, or provide opening permission. Those remain disabled;
all user-selected browser/PDF apps, scanner protections, Chrome settings,
and native host access are unchanged. The test uses only loopback traffic,
never reads an actual user's PDFs, and removes the disposable profile.

## Firefox's built-in PDF viewer: real-browser check (opener-0803)

The dedicated **Firefox built-in PDF viewer smoke test** GitHub Actions job
installs Mozilla Firefox (latest release channel) and geckodriver, and runs
Firefox in a **new disposable headless profile** with its built-in PDF.js
viewer enabled. The test creates a valid, small, one-page PDF in memory and
serves it only over an ephemeral `127.0.0.1` HTTP listener with inline
`Content-Type: application/pdf` and `Cache-Control: no-store` headers.
It tests both a normal `.pdf` path and an extensionless MIME-identified path.

The test requires real local PDF requests plus **actual rendered PDF.js
evidence** in the browser document: the built-in viewer and page controls,
PDFViewerApplication with an initialized one-page PDF document, and a rendered
first page. HTTP success, a filename suffix, the mere presence of an empty
viewer shell, or a downloaded PDF are not sufficient for a pass. The test
fails if Firefox or geckodriver is missing, the document cannot open, or the
built-in reader is disabled. See
[`test-firefox-pdf-viewer.mjs`](../extensions/webextension/scripts/test-firefox-pdf-viewer.mjs)
and its [regression checks](../extensions/webextension/tests/firefox-pdf-viewer.test.mjs).

The check does **not** install or activate the PDF Magic WebExtension, grant
browser permissions, call native messaging, run ClamAV, or establish that
the viewer can be intercepted before rendering. This verifies the native
**Firefox PDF.js viewing path**, not scanner authority or pre-open
enforcement, which remain inactive. User PDF files, browser profiles,
preferences, and preferred PDF applications are never accessed or changed.
Temporary test profiles and the loopback listener are disposed after the run.

## Safari's PDF viewing: real browser verification (opener-0804)

CI's **Real Safari PDF viewer behavior** check uses Apple's own
`/usr/bin/safaridriver` on a disposable macOS runner. It enables
remote automation for that runner, creates an isolated Safari WebDriver
window and visits two pages hosted solely on `127.0.0.1`: a `.pdf`
URL and an extensionless URL with `Content-Type: application/pdf`.
Both responses have `Content-Disposition: inline` and contain a
generated, harmless, single-page PDF; each renders a large, different
colored rectangle.

The test requires a real Safari WebDriver session, a successful local
PDF request, the PDF's navigation URL, and a browser-viewport screenshot
showing a substantial region of the PDF's **actual rendered color**.
It does not equate a network request, content type or URL alone with
successful viewing. An unavailable Safari automation session, blank viewer,
download-only outcome, navigation error or missing color makes CI **fail**;
there is no silently skipped browser check. The portable self-test covers
PDF structure, loopback-only response headers, strict 404 behavior, and the
PNG color detector, without pretending to be a Safari test.

The automated smoke test only establishes that the *tested* macOS Safari
build can display inline PDFs from the two local HTTP paths. It does not
test toolbar features, private windows, remote URLs, blob/file URLs,
automatic interception, native scanner gating, or an actual production
file handoff. Safari WebDriver's automation windows are isolated from
normal user browser settings; no Safari extension is installed. The
existing PDF Magic Opener scanner and selected application preferences
are never touched. See [Apple's Safari WebDriver guidance](https://developer.apple.com/documentation/webkit/testing-with-webdriver-in-safari).

## Vendor documentation

- [Google Chrome — Manage PDFs](https://support.google.com/chrome/answer/16215622?hl=en)
  describes viewer navigation, form controls, annotations, and OCR.
- [Mozilla Firefox — View and edit PDFs](https://support.mozilla.org/en-US/kb/view-pdf-files-firefox-or-choose-another-viewer)
  describes the PDF viewer, annotations, forms, and visible signatures.
- [Mozilla PDF.js](https://github.com/mozilla/pdf.js)
  identifies the rendering library integrated into Firefox.
- [Apple — Preview for Mac](https://support.apple.com/guide/preview/get-started-prvw846b61d3/mac)
  describes the separate macOS app's PDF editing and Markup functions.

These resources describe their respective products, not promises of feature
parity or of approval by PDF Magic Opener.
