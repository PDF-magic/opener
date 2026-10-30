# Completed download filename lookup (opener-0676)

`retrieveCompletedDownloadFilename(downloadsApi, permissionsApi, completion)` is
an explicit, one-shot, browser-neutral lookup for a completion notice shaped
`{ kind: "completed", id }`, as emitted by `subscribeToDownloadCompletions`.
It returns a Promise resolving to a frozen `{ id, filename }` or `null`.

Because `downloads.onChanged` completion updates may contain only a state
delta, the filename cannot reliably be read from the completion event itself.
The module uses the browser-supplied completed download **ID** to perform
exactly one `downloads.search({ id })` after verifying that the browser
currently grants the optional `downloads` permission. It attaches an existing
permission-revocation observer *before* the grant check, and discards results
when permission is removed during the check or lookup. Denied or unsupported
permissions, rejected searches, and ambiguous results fail closed without
surfacing browser error strings.

The result must identify **exactly that ID** with `state: "complete"` and a
nonempty, bounded filename string without control characters. Only its
filename and ID are returned; URLs, referrers, cookies, browser headers,
content and other metadata are not copied. The filename may be the browser's
**absolute local path**, so treat it as sensitive and untrusted: never log,
persist, expose to a webpage, or send directly to a native messaging host.
No full history query or automatic background monitoring occurs.

**Filename retrieval is not a verified scan, file integrity proof,
quarantine decision, or authorization to open a PDF.** Download IDs can be
reused or removed between the completion event and lookup; a future trusted
integration must revalidate file identity and all existing ClamAV freshness,
complete-scan, integrity, quarantine and selected-application safeguards.
An absent filename cannot imply a clean file.

This module does not import browser globals, request permissions, start a
scan, open files, alter user preferences or activate the shipped inert
background. Only a separately reviewed user-approved integration may invoke
it. The `scanner-tests` CI job automatically discovers
`tests/download-filename.test.mjs` in the WebExtensions `npm test` suite.
