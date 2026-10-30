# Shared WebExtensions project (opener-0560)

This private, dependency-free Manifest V3 project is the common starting point
for future browser integrations. The shared browser extension display name is
**PDF Magic Opener** (opener-0561). This is a stable product name, not a claim
that the extension is currently installable or active. It is not a packaged, installed, or activated
extension, and is not wired into the native PDF Magic Opener application.

The manifest description identifies PDF Magic Opener as the intended future
browser integration and explicitly warns that this inactive scaffold cannot
scan, sanitize or open PDF files. It must not advertise protection before
runtime integration is implemented and reviewed.

From this directory, with Node.js 20 or newer:

```sh
npm run build
npm test
```

The shared Manifest V3 `action` displays the existing PDF Magic Opener icon
in the browser toolbar with the truthful title **PDF Magic Opener (not active)**.
It opens a static, accessible **Not active** popup with no controls, scripts,
PDF scanner or launch behavior. Active interactions require separate review.
The Chromium and Firefox builds package local toolbar icons and the fixed
`popup.html` and `popup.css` assets without adding permissions or host access.
The popup does not read browser state, user preferences or document contents.
The build rejects scripts, remote links, active controls and symlinked assets.

The build writes `dist/manifest.json`, packages an inert `dist/background.js`
Manifest V3 module service-worker entry point from `src/background.js`, and copies
the four source PNG icons
(16, 32, 48, 128 pixels) into `dist/icons/`. These are original local artwork:
a violet rounded tile, white folded PDF page, and gold sparkle. The manifest
references only these static assets; no image requires a network request.
The build validates format, dimensions and exact local paths. Tests decode PNG
pixels and verify output bytes match source art. `dist/` is ignored by Git. The project deliberately includes
no browser-specific configuration, active background listeners, content scripts,
permissions, host access, or native messaging. The registered service worker is
intentionally a no-op module: it does not inspect documents, handle browser
events, send messages, or contact the native application. Firefox-specific
background registration belongs to its separate manifest task. Browser-specific targets and
useful extension functionality must be introduced in separately reviewed work.

**Security boundary:** A built manifest is not a PDF scan or opening approval.
Future integrations must use the established ClamAV freshness and file-integrity
gates and verified application handoff, preserve quarantine protections, and
respect the user's selected PDF destination. No browser extension can claim
that a PDF was verified merely because this project builds successfully.

## Open native preferences (opener-0577)

The inactive toolbar popup now contains one user-initiated **Open PDF Magic
Preferences** link. It requests the local macOS `pdfmagicopener://preferences`
URL, registered by the separate installed native preferences app. Browsers may
request permission to launch an external app. A missing app cannot be launched.
The extension itself cannot scan, open or approve PDFs, and no website, native
messaging, tab or browser permission is required. See
[`preferences-action.md`](preferences-action.md).
