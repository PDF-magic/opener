# PDF MIME evidence from navigation response metadata (opener-0738)

`detectPdfResponseMime(details)` is a passive, browser-neutral classifier for
**top-frame navigation response MIME metadata** supplied by a trusted browser
API. Unlike completed-download MIME detection (§11.1) or PDF-suffixed URL
navigation detection (§12.1, opener-0737), this checks MIME evidence in a
response without consulting a filename or URL.

When a supported and separately permission-authorized browser API exposes
`responseHeaders` (such as `webRequest.onHeadersReceived` with response
header access), the helper reads exactly one `Content-Type` value. It also
supports a directly exposed `mimeType` data field from compatible APIs. It
accepts the existing strict MIME grammar and the shared candidate detector's
`application/pdf` and `application/x-pdf` aliases, including valid parameters
and case variation. Unsupported APIs, absent metadata, non-PDF types, duplicate
or conflicting declarations, invalid headers and malformed events return
**no PDF candidate**.

The event must identify a real tab (`tabId` nonnegative safe integer),
`frameId: 0` and `type: "main_frame"`. Values come only from own data
properties; getters and proxy errors fail closed. Results are frozen and
contain only `{ isPdfCandidate, evidence, authorizesOpen: false }`, never
response headers, URLs, cookies, filenames or private navigation details.

**Declared MIME is untrusted candidate evidence, never verified PDF bytes,
malware cleanliness or a permission to open.** This module never registers
listeners, requests `webRequest`/host permissions, fetches response bodies,
connects native messaging, changes the browser's download behavior, or
alters existing scanner/ClamAV protections and saved user preferences.
The shared WebExtension background remains intentionally inactive. Live
response-header observation requires a separately reviewed and user-authorized
browser integration; APIs that do not expose MIME cannot provide it here.

`tests/pdf-response-mime.test.mjs` runs in `npm test` and explicitly in
required CI to verify supported metadata, unsupported browsers, malformed
or hostile input, privacy, and unchanged extension permissions.
