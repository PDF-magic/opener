# Explicit Scan This PDF: cross-origin restrictions (opener-0768, §12.2)

`assessExplicitPdfCrossOrigin({ request, coordinator, permissionsApi, manifest })`
provides an **inactive, fail-closed** origin and permission policy for the
explicit Scan This PDF action. It is separate from the user-consent gate,
download acquisition and native scan coordinator. Merely identifying a PDF
or granting a browser host permission does **not** authorize a network fetch,
read its contents, submit a native scan or open the PDF.

A future, independently authenticated integration must inject
`crossOriginPdfReady: true` and an own synchronous
`readVerifiedPdfOriginContext(reference)` method, returning an exact
verified, permission-checked snapshot of the currently selected PDF:
`requestId, tabId, frameId, selectionId, resourceId, documentOrigin, resourceOrigin, verified: true, permissionGranted: true`.
The request uses the existing validated explicit-scan descriptor. The
coordinator must authenticate the initiating browser tab and frame, the
selected document, and the **final PDF resource origin after any redirect**.
Raw URLs, page-provided origin claims and credentialed fetch metadata must
never masquerade as verified context.

* **Same origin:** report `same-origin` with no host-permission check.
  This is only an origin classification, not file-read or scan permission.
* **Different origin or subdomain:** report `cross-origin-restricted`
  unless the Manifest V3 extension **explicitly** declares the exact HTTPS
  destination in its optional host grants and the browser confirms its
  current permission. Wildcards and required host permissions do not count.
  No permission prompt is issued here; granting an optional host must be
  a separate explicit user action.
* **Verified cross-origin site grant:** after subscribing to permission
  removal, two separate `permissions.contains({ origins: [pattern] })`
  checks, and a fresh identical selected-document verification, report
  `cross-origin-site-grant-verified`. This status is never a CORS
  bypass or an assertion that a PDF is accessible; network response policy,
  cookies, authentication, redirects, and native file integrity must still
  be verified independently by a separately reviewed acquisition flow.
* **Invalid, stale or inaccessible evidence:** return `unavailable`
  without silently downloading or suggesting a bypass. During permission
  checks, any site-permission removal latches a restricted outcome. All
  results are frozen, omit browser URLs and sensitive paths, and explicitly
  set authorizesFetch/authorizesScan/authorizesOpen to false.

The shipped WebExtension currently has **no host permissions or optional
host declarations**, and its background worker remains inert. This task
does not add permissions, register listeners, scrape cross-origin frames,
fetch with privileges, bypass CORS, or change scanner security or user
preferences. A functioning authenticated browser-to-native selection and
scan bridge, consent and permissioned download integration remain
prerequisites. Native ClamAV signatures, quarantine, file identity and
scan-before-open policies remain mandatory.

The `tests/explicit-pdf-cross-origin.test.mjs` suite covers same
origin, subdomain/redirect restrictions, exact optional grants, denial,
permission removal, stale selections, hostile metadata, and absence of
network/native side effects. The existing WebExtensions `npm test`
CI glob automatically runs these tests.
