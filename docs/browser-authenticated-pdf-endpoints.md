# Authenticated PDF endpoint browser verification (opener-0806)

The real Chrome for Testing and Mozilla Firefox browser smoke suites exercise
**PDFs behind an authenticated HTTP endpoint**, not merely public PDFs or
mocked authentication failure classifications.

Each run builds a one-page PDF in memory and serves it through a disposable
`127.0.0.1` HTTP server. The server requires a fresh, randomly generated
per-run session cookie for `/auth/private.pdf` and returns a **401 plain-text
response** when that cookie is missing or wrong. The browser first navigates
to the protected PDF without signing in; the test checks that it displays the
authentication-required response and that the PDF bytes have **not** been
served. It then navigates to a local sign-in page, where the server sets an
`HttpOnly; SameSite=Lax; Path=/auth` session cookie. The test confirms that
the page cannot access the cookie using `document.cookie` and navigates back
to the protected PDF in the **same browser session**.

A pass requires that the server actually grants a PDF response with the
browser-held session cookie and that the browser shows the built-in PDF
viewer. Chrome for Testing must show its PDF extension frame or PDF embed;
Firefox must show its initialized PDF.js document, the viewer controls, and
a rendered first page. The test checks ordinary unauthenticated and
extensionless PDFs separately, as required by the existing viewer suites.

The fixture is
[`authenticated-pdf-routes.mjs`](../extensions/webextension/scripts/authenticated-pdf-routes.mjs),
with direct HTTP-negative and positive regression cases in
[`authenticated-pdf-endpoints.test.mjs`](../extensions/webextension/tests/authenticated-pdf-endpoints.test.mjs).
Both existing CI browser jobs invoke the enhanced
[`Chrome smoke test`](../extensions/webextension/scripts/test-chrome-pdf-viewer.mjs)
and [`Firefox smoke test`](../extensions/webextension/scripts/test-firefox-pdf-viewer.mjs).
The Node regression tests run with the existing WebExtensions `npm test` glob.

These are **synthetic local sessions**, never accounts, passwords, user
cookies, private documents, real-site endpoints, or network services. They
verify the browser's own authenticated PDF rendering, not the PDF Magic
Opener extension's ability to access authenticated pages or intercept
rendering. The existing extension has no authenticated native ClamAV
scan-before-open integration, so interception remains disabled. Authentication
to third-party sites, SSO, proxies, cross-origin cookies, signed URLs and
user-scoped downloads require separate browser and native integration review.

All traffic is loopback-only, no session value is logged, no production
browser profile is touched, and user preferences, native scanner safety
checks, browser permissions, quarantine and default PDF-opening behavior
remain unchanged. Browser processes, profiles and servers are cleaned up by
their existing smoke harnesses.
