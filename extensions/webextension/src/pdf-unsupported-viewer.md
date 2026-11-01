# Handle unsupported PDF viewer implementations (opener-0796)

**Scope:** a passive, fail-closed viewer compatibility decision for future
optional automatic interception. The shared browser extension is currently
inactive: its background worker has no listeners, host permissions, or native
scanner connection. This change does not claim otherwise.

## Unsupported viewer detection and response

A separately authenticated browser coordinator may call
`assessUnsupportedPdfViewer(browserId, context)` with its **trusted
browser-generated** tab/frame/document URL and a independently verified
viewer-kind classification. The `trustedBrowserEvent` Boolean is merely a
required assertion by the coordinator: it cannot authenticate an event on its
own. Never construct such a context from a site script or a content-script
message and assume it is trusted.

The assessment reuses existing strict browser-owned PDF shell recognition
for Chromium and Firefox and existing conservative site-hosted PDF.js URL
classification. Browser-owned viewer shells, PDF.js canvas viewers, plugin
renderers, embedded viewers and custom scripted viewers are all considered
**unsupported for reliable automatic scan-before-render interception**.
A known viewer URL is not evidence that PDF bytes were acquired or scanned.

Unexpected privileged pages, cross-browser viewer identities, and unknown
viewer kinds are `unverified-viewer`, not automatically supported or
automatically interceptable. Ordinary pages with no viewer evidence report
`not-a-viewer`, not a presumed PDF. All statuses return immutable, URL-free
results: no automatic holding-screen redirect, no viewer document fetch,
no automatic scan, no opening, and no assertion that the browser's native
preview has been blocked.

For unsupported or unverified viewers, the safe next step is to **offer an
explicit Scan This PDF workflow only after its separate eligibility,
permission, consent, PDF acquisition, ClamAV and native handoff validations**.
When that workflow cannot acquire the PDF safely, explain that this viewer
cannot be intercepted and leave the user's original browser state unchanged.
Do not silently download a URL from a viewer query string, scrape privileged
pages, rewrite the viewer, replace the browser's PDF handling preferences,
or claim that a visible PDF passed a scan. The browser may still display
that PDF independently of PDF Magic Opener.

## Browser limitations and related tasks

Chromium's built-in viewer and Firefox's PDF.js resource viewer have
privileged origins and may not expose the underlying PDF bytes to an
ordinary WebExtension. Site-hosted custom viewer canvases, embedded frames,
blob/data/file paths, cache and internal browser viewers vary by browser.
A network observation or suffix hint does not guarantee synchronous
render blocking. The separate opt-in (opener-0783), holding screen
(opener-0785), handoff (opener-0784), scan restoration (opener-0788)
and multi-tab session (opener-0792) tasks remain outside this PR.

Scanner freshness, canonical PDF identity, complete ClamAV verdict,
quarantine, fail-closed native opening, and the user's configured destination
application remain authoritative. No new privileges, browser preference
changes, native scanner changes, or live interception are introduced.

The focused Node suite checks browser-native shell matching and mismatching,
PDF.js, scripted/plugin/embedded viewers, unknown internal pages, malformed
or hostile metadata, unchanged permissions and privacy. The existing
WebExtensions `npm test` glob runs this suite in required GitHub CI.

## Browser compatibility: unsupported inline cases (opener-1070)

The existing real **Firefox browser-native PDF downloads** CI job also
exercises three negative inline-viewer cases in a fresh, throwaway Firefox
profile. It disables `pdfjs.disabled` only **as a true Boolean preference**
(`"pdfjs.disabled": true`), without touching any installed browser settings.

- A valid `application/pdf` response marked `Content-Disposition: inline`
  must be saved intact when Firefox's built-in PDF.js is disabled.
- A valid PDF served as `application/octet-stream` with an inline disposition
  must also be downloaded rather than treated as an active PDF viewer.
- A `.pdf`-looking URL served as `text/html` must remain an HTML page,
  not an inferred PDF preview, download or scanner-clean result.

Real WebDriver clicks, exact saved bytes, response counts, correct MIME headers
and an HTML document check make these browser-level regressions rather than
just simulated metadata assertions. They run inside the existing
`firefox-native-pdf-download` job; the same fixture remains loopback-only,
and the test continues to require temporary-profile cleanup.

**Unsupported for automatic interception does not mean a browser cannot
open the PDF.** A browser may download or display content independently.
This test verifies only the tested Firefox profile's behavior, not a working
PDF Magic interception mechanism, ClamAV verdict, external PDF application
handoff or behavior across all installed browsers. The shipped extension's
inactive background, minimal permissions, native scanner safety and user
customizations are unchanged.
