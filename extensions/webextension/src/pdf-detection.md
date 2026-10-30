# Shared PDF candidate detection (opener-0571)

`pdf-detection.js` exports `detectPdfCandidate({ url, mimeType, filename })`, a
synchronous, browser-neutral metadata classifier. Future Chromium, Firefox and
Safari integration code can use the **same** classifier for PDF candidates
without accessing remote content, local files, browser APIs or scanner state.

```js
import { detectPdfCandidate } from "./pdf-detection.js";

const result = detectPdfCandidate({
  url: "https://example.invalid/document.pdf?download=1",
  mimeType: "application/octet-stream"
});
// { isPdfCandidate: true, evidence: "url-path", authorizesOpen: false }
```

The module considers canonical `application/pdf` and `application/x-pdf`
Content-Types, then suggested `.pdf` filenames or final URL path components
(including percent-encoded path characters and case-insensitive suffixes).
Query parameters and fragments are never treated as filenames. A known
non-PDF MIME type overrides suspicious `.pdf` URL or filename hints. Only
`http:`, `https:` and `file:` URLs are eligible for path hints; the classifier
does **not** access files or grant file URL permissions. Invalid metadata,
non-string fields, getters and oversized values return a non-candidate result.
The return value is immutable and does not contain URLs, filenames or user data.

**A candidate is not a valid, scanned or safe PDF.** The returned
`authorizesOpen` flag is always `false`; detection cannot authorize browser
redirection, downloading, opening, removing quarantine, reading bytes or
bypassing the installed mandatory ClamAV scan/signature/integrity gate or the
user-selected application preference. The existing extension remains inactive.
Background listeners, browser permission requests and native communication are
separate checklist tasks.

The existing `npm test` script discovers `tests/pdf-detection.test.mjs`, and
the required `scanner-tests` GitHub Actions workflow already runs the shared
WebExtensions build and test scripts. No new CI workflow is required.
