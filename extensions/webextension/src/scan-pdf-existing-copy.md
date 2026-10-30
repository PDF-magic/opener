# Existing downloaded copy lookup for Scan This PDF (opener-0761)

The passive findExistingDownloadedPdfCopy(downloadsApi, permissionsApi, selection)
helper finds a browser-reported completed download of the same current PDF
source. An independently authenticated coordinator supplies the exact
{ kind: "trusted-current-pdf-source", url } selection; a page-controlled
URL or PDF-looking suffix must never establish document identity.

After an explicit current optional downloads permission check, the helper
watches revocations and download create/change/erase events throughout the
lookup. It searches with an escaped exact HTTP(S) URL filter and independently
checks the returned URL, ignoring only viewer fragments such as #page=2.
Missing, ambiguous or invalid search records fail closed. The helper then
reuses existing permission-checked exact-ID methods to establish a syntactically
absolute completed-download local path, matching source URL and a final strict
preflight. The last preflight requires browser exists:true, no paused, resumable,
incomplete or interrupted state, and consistent nonzero transfer byte counts.

An affirmative result is frozen and contains only the browser download ID and
flags: kind:"existing-browser-download-candidate",
browserReportsExistingCopy:true, nativeFileVerified:false,
requiresNativeRevalidation:true, scanVerified:false, authorizesScan:false,
authorizesOpen:false. It never includes the private source URL or local path.

Any failure returns null (unknown/unavailable), never proof that the real
filesystem lacks a copy. Browser history can be stale, and exists:true is
browser metadata, NOT a native filesystem existence or file-identity check.
Different source URLs, multiple matches and externally relocated files are not
claimed to match. A separately authenticated native coordinator must recheck
canonical file identity and stability immediately before any scan, and preserve
mandatory ClamAV freshness, full-file integrity, quarantine and user-selected
application opening protections.

No permissions are requested; nothing is downloaded, opened, scanned, logged
or persisted. The extension background remains inert, with no manifest or
user-customization changes. Tests in tests/scan-pdf-existing-copy.test.mjs
exercise exact matching, races, missing or stale downloads, revocation, hostile
metadata, privacy and scanner invariants. They run via npm test and the
dedicated required scanner-tests CI step.
