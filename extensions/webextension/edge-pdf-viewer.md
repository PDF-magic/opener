# Per-browser verification: Microsoft Edge built-in PDF viewer (opener-0802)

The Windows Edge compatibility job now tests **the browser's actual built-in
PDF viewer**, separately from the existing PDF Magic Opener extension-popup
smoke test and native scan-before-open application-target tests.

The `edge-pdf-viewer.test.mjs` regression creates a valid, deterministic,
one-page local PDF in memory (no repository PDF fixture or user document).
A temporary HTTP server bound only to `127.0.0.1` delivers that fixture with
`Content-Type: application/pdf` and `Content-Disposition: inline`.
An independent HTML control response confirms the browser first navigates
normally. A real, Windows-installed Microsoft Edge and matching EdgeDriver,
already provided by the `edge-compatibility` job, then navigate to the PDF.
The test checks:

- Edge requests the in-memory PDF, shows its original loopback URL and reports
  the PDF MIME type instead of remaining on the HTML page or downloading it.
- A built-in `application/pdf` embed/object element has positive rendered
  geometry; merely receiving a PDF response is not enough to pass.
- The fixture has a correct PDF cross-reference table and no active
  JavaScript, launch actions or external resources.

A **fresh, disposable profile** prevents touching any user's Edge PDF viewer,
default-handler, download or extension settings. The driver uses local
WebDriver control and a loopback-only PDF source, not external websites or
scanner jobs. Browser profile cleanup and WebDriver teardown run even when a
test assertion fails. This smoke test does not install an extension, enable
automatic interception, initiate a native scan, override selected PDF
applications, or change ClamAV/quarantine behavior.

Microsoft Edge's PDF viewer implementations and enterprise policies can
change. This test verifies supported **observable behavior** on the pinned
Windows runner's installed Edge/EdgeDriver pair; it does not assume Chrome's
toolbar controls, Adobe-specific features, the same DOM implementation in
every Edge version, or an installed macOS PDF handler. It will fail if
the installed test browser downloads the PDF instead of displaying it; do
not weaken that result by manufacturing a viewer DOM node or overriding
PDF policies. In particular, a direct browser navigation to an untrusted
PDF is *not* evidence that PDF Magic Opener successfully intercepted or
scanned it.

**Prerequisite for enforcing scan-before-view:** the separately reviewed
optional browser interception feature needs authenticated native scanner
coordination and an effective pre-render request hold. The current extension
background remains inert and this task does not claim to block arbitrary
Edge PDF viewer navigations.

Run locally:

```sh
cd extensions/webextension
npm run build
node --test tests/edge-pdf-viewer.test.mjs
```

The PDF structure and safety assertions run without Edge. The live browser
case is skipped unless `EDGE_WEBDRIVER_BINARY` is set; the required Windows
`Microsoft Edge compatibility (Windows)` CI job sets this variable and
runs the full live browser case as a separate step. No external npm
dependencies are needed.

See the [existing Edge extension smoke test](edge-compatibility.md) and
[PDF viewer differences](../../docs/browser-pdf-viewers.md).
