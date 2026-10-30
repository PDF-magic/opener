# Detect PDFs with misleading download extensions (opener-0682)

`detectMisleadingPdfExtension(mimeRecord, filenameRecord)` is a synchronous,
pure, browser-neutral classifier that compares the outputs of the existing
permission-checked completed-download MIME and filename lookups. Pass the
frozen `{id, mime}` record returned by `retrieveCompletedDownloadMime` and
the `{id, filename}` record returned by `retrieveCompletedDownloadFilename`
for the **same** completed browser download. The classifier performs no
download lookup, filesystem access, networking, or listener registration.

Both records must contain exactly the specified own data properties and a
matching nonnegative browser ID. Malformed, accessor-backed, unexpected,
oversized, or missing metadata is rejected with `null`. Only valid
browser-declared PDF MIME (`application/pdf` or `application/x-pdf`,
including legitimate parameters) can establish a **PDF candidate**.
If its last filename component does not end with a standalone,
case-insensitive `.pdf` suffix, the frozen result has
`hasMisleadingExtension: true`. Examples include `report.txt`,
`report.pdf.exe`, and extensionless files, including downloads into
absolute POSIX or Windows directories. A PDF suffix alone cannot override
a declared non-PDF or generic MIME type. The result includes only the ID,
boolean flags, a fixed evidence label, and `authorizesOpen: false`; it
never contains the sensitive MIME string, filename or path.

**A browser-declared MIME type is not content verification.** A web server,
download response or browser can mislabel bytes. A future trusted native
coordinator must independently verify actual PDF content, canonical file
identity and the mandatory ClamAV signature freshness, full-file scanning,
integrity, quarantine and user-selected application safeguards. Browser
download IDs can be reused between separately timed metadata lookups.
This comparison cannot authorize scanning, opening, or bypassing any gate.

This does not activate the intentionally inert background worker, request
permissions, read local file bytes, send native messages, modify settings or
retain user metadata. The user-authorized download integration must obtain
the two metadata records separately with effective downloads permission and
revocation checks. The `tests/download-misleading-extension.test.mjs` suite
is automatically executed by the existing WebExtensions `npm test` step
within the repository's `scanner-tests` GitHub CI job. Existing
`pdf_format_identification.py` remains the distinct bounded, read-only
native header-inspection primitive and is not changed by this task.
