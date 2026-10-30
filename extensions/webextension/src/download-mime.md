# Retrieve the browser-declared MIME type (opener-0678)

`retrieveCompletedDownloadMime(downloadsApi, permissionsApi, completion)`
performs an explicit one-shot lookup for a `{ kind: "completed", id }` event
from the existing `subscribeToDownloadCompletions` adapter. Returns a frozen
`{ id, mime }` record or `null`. A completed browser event can contain only
a change-of-state delta, so its declared MIME type must be retrieved from the
browser's current `downloads.search({ id })` result instead.

This module uses only the exact completed download ID. Before querying, it
requires a current, positive `permissions.contains({ permissions: ["downloads"] })`
result and subscribes to permission removals. A revocation during an
asynchronous check or lookup drops the result. Unsupported APIs, missing
permission-revocation support, no matching record, more than one result,
mismatched ID, incomplete state, missing MIME or malformed MIME fail closed.
The MIME value is preserved as declared by the browser, with a bounded
length and basic MIME syntax validation. No filename, URL, referrer, cookies,
headers, file bytes or browsing history are copied or retained.

**A declared MIME type is untrusted metadata, not content sniffing, PDF
identification, or proof that the file is malware-free.** It cannot authorize
a scan result, circumvent ClamAV freshness/integrity/quarantine requirements
or open the PDF in the user's chosen application. If the MIME declaration is
missing or misleading, consumers must not infer safety or file type from it.
Download IDs can be reused or invalidated before lookup. A future coordinator
must independently verify actual file identity and scanner results.

The module has no import-time behavior, does not request permission,
activate the inert browser background worker, send native messages, scan or
open files, or change any user preference. A separately reviewed, user-
authorized integration must invoke it. The ten tests in
`tests/download-mime.test.mjs` run within the existing WebExtensions
`npm test` suite in the repository's required `scanner-tests` CI job.
