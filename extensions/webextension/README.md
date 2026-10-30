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

The build writes only `dist/manifest.json`, a reproducible copy of the common
source manifest. `dist/` is ignored by Git. The project deliberately includes
no browser-specific configuration, runtime background script, content script,
permissions, host access, or native messaging. Browser-specific targets and
useful extension functionality must be introduced in separately reviewed work.

**Security boundary:** A built manifest is not a PDF scan or opening approval.
Future integrations must use the established ClamAV freshness and file-integrity
gates and verified application handoff, preserve quarantine protections, and
respect the user's selected PDF destination. No browser extension can claim
that a PDF was verified merely because this project builds successfully.
