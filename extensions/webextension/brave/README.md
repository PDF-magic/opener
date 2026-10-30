# Brave WebExtensions compatibility (opener-0599)

Brave is a Chromium-based browser. It consumes the same validated unpacked
Chromium Manifest V3 build as Chrome; a new Brave-specific manifest, extra
host permissions, native messaging grant or browser identity spoof is neither
necessary nor authorized.

## Automated compatibility coverage

The scoped GitHub Actions workflow
.github/workflows/brave-webextension.yml installs the **real Brave Stable**
browser using the signed package feed and instructions published at
https://brave.com/linux/. It runs only for WebExtensions-related changes
(and manually when requested), not for unrelated changes to native macOS
scanner code.

The workflow builds the existing extension with npm run build, performs
manifest and asset tests, and launches Brave headless with an **isolated
temporary user profile** and the built unpacked extension. A CI-only
playwright-core automation driver targets /usr/bin/brave-browser directly;
it is not a Chromium substitute and adds no runtime dependency to the
extension's package. The smoke test verifies that Brave:

- Loads the actual Manifest V3 extension service worker.
- Exposes the exact safe manifest: no required permissions or website hosts,
  the independently consent-gated optional downloads API, and private-window
  exclusion (incognito not_allowed).
- Serves the bundled local popup with its expected title and inactive status,
  disabled Scan PDF control and verified-scanner-unavailable explanation.
- Preserves the expected local stylesheet and fixed native preferences link.
- Does **not** silently grant the optional downloads permission.

The test fails instead of claiming Brave compatibility if Brave is absent,
cannot launch, does not install the extension, cannot serve its popup, or
unexpectedly enables the disallowed privileges or Scan PDF action. It does
not load user web pages, access actual PDF files, request user permissions,
scan, contact a native messaging host, or launch a destination app. The
temporary browser profile is removed even when an assertion fails.

The separate existing macOS Brave PDF *destination* tests validate safe
native application handoff, not WebExtension loading. This task adds the
missing **real browser extension** compatibility test without changing those
tests or weakening scanner integrity, quarantine, ClamAV signature freshness,
or saved user settings.

## Manual confirmation

After a successful npm run build, open brave://extensions in a current
Brave desktop browser, enable developer mode and load the unpacked
extensions/webextension/dist directory. Verify the extension is labeled
PDF Magic Opener, that its popup displays **Not active**, and that **Scan
PDF is disabled**. Do not grant optional downloads access or enable
private browsing as part of this test.

This checks the existing inactive scaffold only. Native scanner
connectivity, popup interactions after a future verified integration,
extension-store publication, and browser-by-browser scanner handoff remain
separately scoped prerequisites.
