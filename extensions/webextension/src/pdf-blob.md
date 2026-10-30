# Identify PDF content from supported blob URL workflows (opener-0747)

The asynchronous `detectBlobPdfContent(details, blob)` helper identifies a PDF candidate only when a separately trusted browser integration has an actual accessible `Blob` associated with a canonical HTTP(S) or opaque-origin `blob:` UUID URL. Valid top-frame and embedded-frame tab contexts are supported.

A blob URL or MIME declaration alone cannot identify PDF content. The helper reads only a five-byte slice and requires the `%PDF-` signature, with an empty, PDF, or generic binary Blob type. Explicitly conflicting MIME, malformed URL/frame metadata, inaccessible Blobs, hostile getters and unsupported schemes return a non-candidate.

**Trust prerequisite:** the caller must independently authenticate the browser observation and URL-to-Blob association, check permissions and consent, and enforce the existing scan-before-open policy. Ordinary extensions cannot generally dereference arbitrary page-created or cross-origin blob URLs, and this module does not try to do so. It does not claim any active production integration.

The result is a frozen `{ isPdfCandidate, evidence, authorizesOpen: false }` object without private URLs, paths, filenames or bytes. A signature is not PDF validity, an antivirus verdict, or permission to open. No browser listeners, script injection, new privileges, networking, native calls, scanner bypass, quarantine changes or user preference changes are introduced. The background remains inactive.

`tests/pdf-blob.test.mjs` is automatically discovered by the existing required CI `npm test` step, covering supported frames, signature/MIME rejection, URL validation, hostile metadata, response privacy, and unchanged extension permissions.
