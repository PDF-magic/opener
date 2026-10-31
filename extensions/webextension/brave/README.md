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


## Brave built-in PDF viewer verification (opener-0801)

The scoped Brave CI now runs **two separate real-Brave checks**. After the
existing extension popup smoke test, Xvfb supplies a virtual display to the
official Brave Stable binary and Playwright runs it **headed**, using a new
isolated profile. A tiny, deterministic **synthetic** PDF is generated in memory
and served only from **localhost** (127.0.0.1, ephemeral port). The test
requests the document with an inline PDF MIME response and verifies that
Brave's **built-in PDF viewer** attaches the exact browser-owned Chromium
PDF component frame while the original tab reports the PDF MIME type, rather
than treating a network response alone as a viewer test.
It checks the PDF response headers, no browser download, no page errors, and
that the PDF Magic Opener extension still lacks its optional downloads grant.
No user document, remote PDF URL, native scanner, or existing browser profile
is used. The isolated browser profile and HTTP server are cleaned up.

**Scope of evidence:** Passing CI verifies an **inline PDF in the fresh
Linux Brave Stable build installed for that workflow run**. It does not
prove behavior for existing user profiles, macOS versions, browser policy
overrides, disabled PDF viewer preferences, download/attachment PDFs,
other browser variants or all PDF navigation paths. Brave's own preferences
may download a PDF instead of rendering it; this is a legitimate user choice.
A successful viewer render is **not** evidence of a ClamAV verdict,
scanner-enforced interception, protection from opening before scanning or
permission to open a user PDF. PDF Magic Opener remains inactive and preserves
all scanner safety and **user** customizations.

For a manual macOS check, use a separate temporary Brave profile, enable its
built-in PDF viewer, and visit a locally served, non-sensitive PDF. Confirm that
the PDF appears in the browser tab. Then separately test a download-preferring
profile and Brave policies; never change an existing user's PDF preferences
or rely on a viewer display as proof of a verified native scan.

## Denied browser permission verification (opener-0812)

The real Brave Stable extension smoke runs against a disposable browser
profile and now attempts a **read-only** `chrome.downloads.search` call
without the optional `downloads` permission. Brave must either expose no
usable API or reject the call. The test fails on unexpected access and
checks `chrome.permissions.getAll()` and `contains()` after the refusal,
confirming that the permission and host-origin lists remain empty. The
popup must still say **Not active** with **Scan PDF** disabled and no
verified scan result. Neither a permission prompt nor a download is initiated.

The companion Node regression runs an explicitly denied optional permission
result through the existing permission-request helper and fail-closed
denial handler. It verifies monitoring shutdown occurs once, a later
purported grant cannot restore operation, and errors cannot leak private paths.

**Boundary:** this is real-browser verification of **API denial without a
grant**, plus a simulated **user refusal** of a future opt-in request. The
inactive production extension does not expose a permission-request button,
so this is not a claim that a live permission prompt was displayed and
dismissed. No browser settings, native **scanner** gates, or **user preferences**
are changed.
