# PDF-related metadata boundary — opener-0596 (§9.2)

The shared extension must **not collect website HTML, DOM content, page text,
browsing history, or unrelated page contents** merely to detect or scan PDFs.

The new pure `classifyPdfDownloadMetadata(event)` function accepts **only**
an already normalized `downloads` event from the shared
`normalizeDownloadEvent` adapter. It rejects raw browser events, unexpected
page-derived properties, symbols, getter-bearing inputs, malformed records,
and non-download events without invoking page APIs. It uses only the
`mime` and final `filename` component to call the existing
`detectPdfCandidate` contract. Known non-PDF MIME types take precedence
over misleading `.pdf` filename suffixes.

The returned value is an immutable record containing **only**
`isPdfCandidate`, `evidence`, and `authorizesOpen: false`. Page text,
document HTML, URL, filename, full local path, download ID, cookies, headers,
and document contents are never returned or retained. The function does not
read PDF bytes, fetch resources, inspect tabs or request any browser grant.

### Future integration

A future explicitly consented download-monitoring integration can call
`classifyPdfDownloadMetadata(normalizeDownloadEvent(kind, downloadEvent))`
and discard non-candidates. **The current background remains inert.**
The helper is not a scanner verdict, permission to open a PDF, or proof
the user authorized monitoring. The caller must establish the separate
`downloads` permission, current consent and scan/native safety boundary
before registering any listener or handling any download.

No `content_scripts`, `tabs`, `scripting`, broad website origin access,
document scraping, page injection or page-content collection is necessary.
The browser manifest and packaged variants are regression-tested for that
constraint; any future page-aware feature requires an independently reviewed
privacy and permission design.

The installed native scanner's signature freshness, file-integrity,
quarantine, scan verdict and user-selected destination restrictions remain
authoritative and unchanged.

`npm test` discovers the new
`tests/page-content-boundary.test.mjs` in the existing required
WebExtensions CI job.
