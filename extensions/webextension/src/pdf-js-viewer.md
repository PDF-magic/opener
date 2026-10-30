# Identify PDFs in JavaScript PDF.js viewers (opener-0746)

`detectJavascriptPdfViewer(details)` in `pdf-js-viewer.js` passively
recognizes candidate PDFs referenced by a site's conventional **PDF.js**
JavaScript viewer route. It accepts only browser-provided, top-frame navigation
events with a valid tab ID and an absolute HTTP(S) URL matching
`/pdfjs/web/viewer.html`, `/pdf.js/web/viewer.html` or
`/pdfjs-dist/web/viewer.html` (case-insensitive, with possible prefix
directories). These commonly use the viewer's single `file` query
parameter for a PDF document URL.

The candidate must have exactly one nonempty `file` parameter resolving to
a **same-origin HTTP(S) URL** whose final path segment is `.pdf`. The
existing shared `detectPdfCandidate` URL-path classifier supplies that suffix
check; a PDF suffix in a query string alone does not qualify. Relative PDF
references and encoded URLs work. Malformed or ambiguous encodings, duplicate
`file` values, unsupported schemes, credentials, cross-origin URLs, oversized
metadata, arbitrary `viewer.html` pages, or unrecognized custom JavaScript
viewer routes return no candidate.

**This is intentionally a narrow heuristic, not PDF verification.** Some
websites build their own viewers or render PDFs from `blob:` URLs, fetch
endpoints without a PDF path, PDF.js defaults with no `file` parameter,
or JavaScript runtime state. Those cannot be reliably identified from these
navigation URL hints alone. Their detection would require a separately
permissioned, privacy-reviewed integration, trusted PDF response MIME
evidence or direct access to page state; none is added here.

The immutable result contains only
`{ isPdfCandidate, evidence, authorizesOpen: false }`; successful matches
use evidence `javascript-viewer`. The classifier never reads page HTML or
JavaScript variables, stores or returns URLs, downloads bytes, follows links,
makes network calls, requests browser permissions, registers listeners,
starts scans or opens documents. The WebExtension background remains inactive.
A future browser integration must independently authenticate browser events
and cannot use candidate evidence to bypass PDF Magic Opener's native ClamAV,
signature freshness, quarantine, file identity, verified scan-before-open or
user-selected application settings.

`tests/pdf-js-viewer.test.mjs` covers supported patterns, misleading
parameters, hostile inputs, privacy, unchanged permissions and CI inclusion.
It runs under `npm test` and explicitly in the required scanner-tests job.
