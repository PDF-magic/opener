# Detect .pdf filenames in completed browser downloads (opener-0680)

`detectCompletedPdfFilename({ id, filename })` is a passive, synchronous adapter
for the immutable result returned by `retrieveCompletedDownloadFilename()`.
It does not query the browser, obtain permissions, monitor downloads or access files.
The caller must have already obtained user consent and checked the current
downloads permission using the existing completed-download filename lookup.

The browser may return an absolute POSIX, Windows or UNC path rather than a
filename alone. This adapter extracts only the last path component in memory
and uses the existing `detectPdfCandidate({ filename })` classifier to check
a case-insensitive standalone `.pdf` extension. Directory names ending in
`.pdf`, trailing slashes, `.pdf.exe`, `.pdf.download`, query strings, URL
schemes, malformed records, accessors and oversized paths do not yield a
PDF filename match. The input remains unchanged.

The result is an immutable `{ id, isPdfFilename, authorizesOpen: false }`
record; invalid records return `null`. The original filename, absolute
path, browser URLs, credentials and other metadata are never returned,
logged or retained. A negative result does not prove a file is harmless.

**A `.pdf` suffix is only an untrusted filename hint, not content
verification, malware clearance or permission to open a PDF.** Scanning,
ClamAV signature freshness, file integrity, quarantine and the user-selected
PDF application remain mandatory, independent checks. This module does not
change scanner behavior, user preferences, extension permissions or the
deliberately inactive background worker.

The nine tests in `tests/download-pdf-filename.test.mjs` are discovered by
the required `scanner-tests` WebExtensions `npm test` CI job.
