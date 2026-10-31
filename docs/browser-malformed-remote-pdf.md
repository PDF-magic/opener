# Malformed remote PDF browser verification (opener-0810)

The existing real Mozilla Firefox PDF.js CI smoke now checks two **deliberately
unrecoverable PDF responses served over HTTP** alongside its valid small,
authenticated and large-PDF cases:

- `/malformed/truncated.pdf` returns a PDF header and incomplete catalog,
  with no referenced pages, xref section, trailer or EOF marker.
- `/malformed/not-a-pdf.pdf` returns non-PDF text bytes while advertising
  `Content-Type: application/pdf` and an inline PDF disposition.

Each route is served by a disposable `127.0.0.1` HTTP listener with an exact
body length, `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`.
The fixture rejects unknown routes and non-GET methods, and verifies a real
browser request for each malformed case. No external URLs, real websites,
private files, credentials, extension permissions or native scanner APIs
are used.

The browser harness first checks the actual PDF.js reader has initialized
and then verifies that the malformed response **does not produce a loaded
PDF document or rendered pages**. Firefox may show an error or an empty viewer;
the test intentionally does not depend on localized error text or treat an
empty PDF viewer shell as successful rendering. It then navigates back to
a generated valid PDF and requires PDF.js to render its one page, ensuring
that each malformed request does not leave the browser session unusable.

The [synthetic server fixture](../extensions/webextension/scripts/malformed-remote-pdf-routes.mjs)
and [HTTP/CI regression tests](../extensions/webextension/tests/malformed-remote-pdf.test.mjs)
run under the existing WebExtension `npm test` suite; the real browser
checks run in the existing
[Firefox smoke harness](../extensions/webextension/scripts/test-firefox-pdf-viewer.mjs)
within GitHub Actions.

**Scope:** This is a real-browser test of two selected, unrecoverably corrupt
remote PDF inputs, not a claim that all malformed PDFs must fail to open.
Some partially damaged PDFs are repairable by PDF.js. This also does not
activate browser interception, verify ClamAV scans, authorize opening a
document, alter native quarantine safeguards or modify the user's selected
PDF application or browser preferences. Existing passive
[PDF structure checks](pdf/malformed-structures.md) remain independent and
inactive in production.
