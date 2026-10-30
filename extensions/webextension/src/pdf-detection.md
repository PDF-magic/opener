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

## Unsupported blob URLs (opener-0748)

Browser-owned `blob:` object URLs are explicitly reported with the frozen,
URL-free result `{ isPdfCandidate: false, evidence: "unsupported-blob-url",
authorizesOpen: false }`. This is distinct from the ordinary `none` result:
the scheme is recognized, but the opaque object URL is not an address the
extension can reliably resolve, retrieve or scan on its own. A `.pdf` suffix
inside a blob URL, browser-supplied PDF MIME or a suggested PDF filename does
not make the underlying object data accessible or malware-safe. These hints
must not cause an unsupported blob URL to be treated as an actionable PDF
candidate. If a browser separately provides a real downloaded file, its
independently authenticated local scan path remains a different integration
task; this classifier never accesses blob bytes.

The detection is passive and does not query the page, fetch object URLs,
create or revoke object URLs, install browser listeners, request permissions,
send native messages, open PDFs, or change user settings or scanner policy.
The existing `tests/pdf-detection.test.mjs` suite covers regular/opaque/
malformed and mixed-case blob schemes, contradictory PDF hints, immutable
path-free outputs, and preserved HTTP(S)/filename detection. That suite
already runs via `npm test` in required GitHub `scanner-tests` CI.

## Unsupported inline data URLs (opener-0749)

`recognizeUnsupportedDataUrl(rawUrl)` identifies the `data:` scheme (case
insensitively), including PDF MIME declarations, generic or malformed data
URLs, without reading or decoding their potentially large inline payloads.
It returns a frozen, private-data-free
`{ isUnsupportedDataUrl: true, reason: "data-url-unsupported", authorizesOpen: false }`
record, or the analogous `false`/`"none"` record for non-data inputs.

For otherwise valid, bounded browser metadata, `detectPdfCandidate`
reports a frozen `{ isPdfCandidate: false, evidence: "unsupported-data-url",
authorizesOpen: false }` rather than accepting misleading PDF MIME or filename
hints. Oversized metadata still fails closed with ordinary `none`.
This classification does not prove PDF contents or authorize loading, fetching,
scanning, opening or bypassing the mandatory local scanner. Browser permissions,
listeners, native messaging and user settings remain unchanged.

Dedicated `tests/pdf-data-url.test.mjs` coverage runs via `npm test` and
also explicitly in required GitHub CI.
