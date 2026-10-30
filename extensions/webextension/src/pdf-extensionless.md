# Detect PDFs served without a .pdf URL extension (opener-0739)

`detectExtensionlessPdfResponse(details)` classifies **main-frame HTTP(S)
responses** where the final URL path does not end in `.pdf` but an
independently supplied trusted browser response positively declares the PDF
MIME type. Examples include `/download?id=123`, `/view`, `/report.bin`
and redirected URLs ending in non-PDF paths.

The classifier composes the existing `detectPdfNavigation` (opener-0737)
and `detectPdfResponseMime` (opener-0738) modules rather than introducing
a second PDF MIME parser or relaxing native scan checks. Only approved
`application/pdf` or `application/x-pdf` response MIME evidence counts.
The trusted response classifier already rejects invalid or conflicting
`Content-Type` headers, malformed direct MIME fields and unsupported
event types.

The URL itself must be a bounded, valid absolute HTTP(S) URL with no
embedded credentials or ambiguous percent encoding. Only main-frame
responses in a nonnegative integer tab can qualify. A `.pdf` appearing
only in a query, fragment, page-provided filename or response URL hint does
not prove content type, and a path ending in `.pdf` remains the distinct
URL-suffix case addressed by opener-0737. Missing or non-PDF MIME metadata
is not enough to classify an extensionless URL. Browser APIs that do not
supply response MIME cannot support this classification without another
separately reviewed detection method.

The result is a frozen, URL-free
`{ isPdfCandidate, evidence, authorizesOpen: false }` record.
**The PDF claim is a candidate only, never inspected or malware-safe PDF
bytes.** This module does not fetch responses, sniff files, add browser
permissions, subscribe to events, intercept downloads, send native messages,
launch a PDF or change scanner enforcement. The extension background stays
inactive. Future approved browser integration must authenticate the event
source, check its permissions and honor the installed fail-closed ClamAV,
signature freshness, integrity, quarantine and verified scan-before-open
requirements; all existing user-selected applications and settings remain.

`tests/pdf-extensionless.test.mjs` covers extensionless paths and queries,
MIME evidence, conflicting/invalid headers, misleading URL suffixes,
malformed and malicious metadata, privacy, and the unchanged inert extension.
The suite runs under `npm test` and as a dedicated required GitHub CI step.

**Dependency:** this focused classifier relies on opener-0738's response
MIME model (PR #498). The implementation must be merged only after that
prerequisite is present in `main`.
