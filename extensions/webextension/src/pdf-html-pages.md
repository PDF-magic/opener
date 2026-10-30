# Avoid misidentifying HTML pages as PDFs (opener-0751)

Browser navigation to a URL ending in `.pdf` **does not prove the response is
a PDF**. An error, login, redirect destination or application page can serve
HTML at that URL. A suggested `.pdf` filename and an HTML page's hyperlinks or
metadata likewise cannot override the actual browser-observed response type.

`classifyHtmlOrPdfResponse(details)` in `pdf-response-mime.js` checks one
explicitly trusted **main-frame browser response event**, using the same strict,
bounded Content-Type parsing and mutually consistent direct/header declarations
as `detectPdfResponseMime`:

- `text/html` and `application/xhtml+xml`, including case and valid MIME
  parameters, yield frozen `{ isHtmlPage: true, isPdfCandidate: false,
  evidence: "html-mime-type", authorizesOpen: false }`.
- Valid `application/pdf` or `application/x-pdf` declarations yield
  `{ isHtmlPage: false, isPdfCandidate: true, evidence: "mime-type",
  authorizesOpen: false }`, **candidate evidence only**.
- Missing, invalid, repeated or contradictory declarations, unknown MIME
  types, unsupported event shapes and untrusted fields yield no classification.
  Neither a PDF-looking URL nor an HTML-looking URL is used as a fallback.

The caller must independently authenticate the browser response source and
check effective permissions. This pure helper **does not** fetch or sniff
response bodies, read browser HTML, inject scripts, register event listeners,
access privileged pages, scan or open documents, or change extension manifests.
A PDF-looking resource whose server lies about `Content-Type` cannot be
resolved without independently authenticated bytes; **the classifier is not
file validation**. A URL-only navigation classifier remains a *candidate* until
response or verified file evidence is available.

The WebExtension remains intentionally inactive. Native ClamAV signature
freshness, file identity and integrity, quarantine and scan-before-open
requirements and user-selected PDF applications remain unchanged. A future
permissioned integration must correlate trusted response metadata to the
matching navigation before using it to suppress false PDF candidates.

`tests/pdf-html-pages.test.mjs` covers HTML masquerading as PDF, truthful
PDF responses, conflicting/missing Content-Type, hostile browser objects,
privacy-safe immutable output and unchanged inactive permissions. It runs
through the existing WebExtensions `npm test` and as a dedicated required
GitHub Actions `scanner-tests` step.
