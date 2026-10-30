# Associate browser download IDs with scan-request candidates (opener-0690)

`associateDownloadIdentifierWithScanCandidate(downloadsApi, permissionsApi, completion)`
builds a **transient, non-authorizing** download-to-scan association. It accepts
only the existing exact-ID `{ kind: "completed", id }` event and returns a
frozen record containing `downloadId`, `browserDownloadIdentifier` (the same
numeric browser ID rendered as a decimal string), an untrusted local `path`,
and explicit `transferComplete: true`, `scanVerified: false`,
`authorizesScan: false`, and `authorizesOpen: false` fields. Failure
returns `null` without leaking browser data or logging errors.

This task **does not initiate a scan request**. The existing native
`scan-and-open.py` scanner already supports the optional
`browser_download_identifier` field on its immutable `ScanRequest`
(opener-0026, merged PR #11), and the command-line input
`--browser-download-id <identifier> <file-path>`. The new helper associates
the same browser ID and path with a candidate before any future trusted
coordinator bridges those layers. The coordinator must explicitly map
`browserDownloadIdentifier` to that existing optional receiving field
without changing the scan target or treating the identifier as authentication.

For one completed download ID, the helper first obtains the syntactically
absolute local path using `retrieveCompletedDownloadLocalPath`, then performs
the stricter **fresh** `preflightCompletedDownloadForScan` check. Each lookup
independently verifies the current optional downloads permission, watches
permission revocations across its asynchronous operations, and queries only
`downloads.search({ id })`. Both results must identify the same download.
The last preflight refuses interrupted, partial, paused, resumable, missing,
temporary-name, zero-byte and inconsistent-length transfers, as defined by
opener-0684. Invalid IDs, missing local paths, denied permissions, revoked
permissions and mismatches fail closed. The helper does not request browser
permissions or activate download monitoring.

**Security limitation:** Two browser metadata lookups cannot prove that a
filesystem path still names the same file, or that another process is not
writing it. Browser IDs may be reused and browser state can change
immediately after the preflight returns. Therefore the record is **only a
correlation candidate**, never a trusted executable scan request, scan
authorization or a malware verdict. A future explicitly user-authorized
native coordinator must recheck permission and download identity as needed,
validate canonical local file identity and file stability immediately before
dispatch, and retain all existing ClamAV freshness, full-file scan, hash
integrity, quarantine and application-opening safeguards. No operation here
sends a native message, accesses files, scans anything or changes settings.

The path remains sensitive and must not be logged, broadcast to webpages or
persisted. The candidate contains no source URL, referrer, cookies, headers,
file bytes, browser danger metadata, or scanner result. The production
WebExtension background remains inactive; no new host permissions or user
customizations are modified.

Regression tests in `tests/download-scan-correlation.test.mjs` cover
successful numeric ID association (including zero and Windows paths),
invalid/mismatched IDs, unsafe or missing paths, completion races,
partial/interrupted transfers, permission denial and revocation, real
completion events, and the inactive scanner boundary. The existing
`scanner-tests` CI WebExtensions `npm test` step automatically runs them.
