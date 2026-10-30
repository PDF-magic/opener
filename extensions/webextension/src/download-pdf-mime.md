# Detect PDF MIME types on completed downloads (opener-0681)

`detectCompletedDownloadPdfMime(record)` is a **pure, opt-in**
classification adapter for the exact frozen `{ id, mime }` record obtained
from `retrieveCompletedDownloadMime` (opener-0678). This is the missing link
between the permission-checked completed-download MIME retrieval and the
existing shared `detectPdfCandidate` PDF candidate classifier (opener-0571).

The adapter recognizes `application/pdf` and the existing shared detector's
`application/x-pdf` alias, case-insensitively and with valid MIME parameters.
Valid non-PDF MIME types, including generic `application/octet-stream`, are
**not** identified as PDF by their filename, URL, or other properties. Invalid,
missing or malformed metadata fails closed. It validates the same MIME grammar
as the retrieval module, requires exactly `id` and `mime` as own data
properties, and never invokes getters or reflects private browser fields.

A valid input yields a frozen, path-free record:
`{ id, isPdfMime, evidence: "mime-type" | "none", authorizesOpen: false }`.
Invalid input yields `null`. A positive result is **only browser-declared
MIME evidence**. MIME may be incorrect or maliciously supplied. It cannot
prove the bytes are PDF, establish malware cleanliness, authorize native
scanning, bypass ClamAV freshness/integrity/quarantine requirements, or open
a document in the user's configured application.

This module never monitors downloads on import, requests permissions, accesses
file bytes, retrieves URLs, activates the inert background worker, or modifies
user customizations. Production use still requires the independently
permission-checked, consented completion and MIME retrieval APIs. The existing
WebExtensions `npm test` / `scanner-tests` CI runs the new
`tests/download-pdf-mime.test.mjs` regression suite automatically.
