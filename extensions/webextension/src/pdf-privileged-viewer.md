# Privileged browser PDF viewer page recognition (opener-0750)

`detectPrivilegedPdfViewer(details)` is a **passive, browser-neutral viewer
shell classifier** for browser-provided navigation metadata. It recognizes
Chromium's built-in PDF component at
`chrome-extension://mhjfbmdgcfjbbpaeojofohoefgiehjai/index.html` and
Firefox's built-in PDF.js viewer asset at
`resource://pdf.js/web/viewer.html`. Query and fragment values are ignored;
they are never read as PDF document URLs or returned in results. Both top-level
and embedded viewer frames may be recognized when a trusted browser API
supplies nonnegative integer `tabId` and `frameId` values.

A matching **viewer page is NOT PDF content evidence**. Even the Chromium
built-in viewer URL can be opened directly without a valid PDF stream;
recognition always returns `isPdfCandidate: false` and `authorizesOpen: false`.
Unknown/internal browser pages (`chrome://`, `edge://`, `about:`,
`moz-extension://`, other `chrome-extension://` IDs) are **not** assumed to
contain a PDF. Firefox extension UUIDs are variable; their paths cannot prove
browser ownership. Untrusted site-supplied strings, malformed metadata,
accessors and proxy traps fail closed, and results are frozen without URL,
filename or document contents.

The caller must independently authenticate the navigation-event source.
Browser-internal pages are privilege-isolated; no attempt is made to read
their DOM, download their embedded content, derive a file from a query
parameter or bypass browser extension permissions. Recognition has no
side effects, listener registration, network activity or native messaging.
The shared extension background remains inert and has no navigation or host
permissions. A separately reviewed integration and appropriate browser
permissions are prerequisites to observing these pages live.

This changes **no** user-selected PDF handler, browser configuration, scanner
operation or open policy. Native ClamAV freshness, PDF identity and integrity,
quarantine and verified scan-before-open checks remain authoritative before
any PDF Magic Opener handoff.

`tests/pdf-privileged-viewer.test.mjs` runs through `npm test` and
explicitly in the required CI workflow. It checks strict viewer identities,
embedded frames, hostile/lookalike URLs, metadata safety, immutable privacy-
preserving results and unchanged inactive extension permissions.
