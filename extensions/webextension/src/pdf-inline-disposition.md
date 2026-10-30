# Detect inline Content-Disposition responses (opener-0741)

The passive `detectInlinePdfResponse(details)` helper identifies
`Content-Disposition: inline` when a **trusted browser-supplied main-frame
response event** exposes it in `responseHeaders` or a directly provided
`contentDisposition` field. It accepts case-insensitive `inline`,
including bounded, well-formed response parameters, and rejects missing,
attachment, duplicated, contradictory, malformed or control-character-bearing
dispositions. It neither reads nor returns response filenames.

The immutable return value is
`{ isInlineResponse, isPdfCandidate, evidence, authorizesOpen: false }`.
An inline disposition alone can mark `isInlineResponse: true` but **never**
identifies PDF bytes. PDF candidacy additionally requires the existing
`detectPdfResponseMime` classifier's independent, valid PDF
`Content-Type` evidence (opener-0738). Unknown, conflicting or
non-PDF MIME leaves `isPdfCandidate: false`. The classifier does not
make assumptions from URLs, MIME guesses or page-provided metadata.

**Scope and prerequisites:** This module is deliberately not wired to a live
browser event listener. A future separately reviewed browser integration must
ensure the event is authentic, permissions are granted, and the browser API
actually exposes headers. Browser APIs with no header access cannot reveal
the disposition. This task does not request webRequest, host or download
permissions; fetch network resources; access document bytes; send native
messages; intercept navigation; initiate scanning; or launch documents.
The shared background remains inactive.

An observed inline PDF *candidate* is not malware-clean and never relaxes
the native scanner's signature freshness, full-file verification, quarantine,
ClamAV, scan-before-open or user-selected application requirements. No saved
preferences change.

The focused `tests/pdf-inline-disposition.test.mjs` regression suite runs
automatically under `npm test` and as an explicit step in required CI.
