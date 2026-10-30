# Recheck downloads moved immediately after completion (opener-0687)

`recheckCompletedDownloadLocation(downloadsApi, permissionsApi, completion, previous)`
is an explicit, one-shot **pre-dispatch** reconciliation step for a download
that may have been moved or renamed shortly after the browser declared it
complete. The caller passes the exact `{ kind: "completed", id }` notification
and the earlier `{ id, localPath }` result from the existing
`retrieveCompletedDownloadLocalPath` helper. It does not subscribe to browser
events or activate the background worker.

The helper rejects malformed snapshots and mismatched download IDs *before*
calling the browser. It re-queries the same download ID through the reviewed
permission-checked local-path retrieval, including the optional-downloads
grant and revocation checks. It additionally reruns the existing
`preflightCompletedDownloadForScan` to refuse missing, deleted, interrupted,
paused, still-writing and temporarily named downloads. A missing, unsupported,
revoked, malformed or conflicting result is **`null`**, never a fallback to
the old path.

An eligible result is frozen:

```js
{
  id: 7,
  currentLocalPath: "/Users/example/Documents/report.pdf",
  browserPathChanged: true,
  requiresNativeRevalidation: true,
  authorizesScan: false,
  authorizesOpen: false
}
```

When the browser reports a different local path, the caller can discard its
stale earlier path and use the refreshed **candidate** only after independent
native verification. An unchanged path sets `browserPathChanged: false`,
but **does not prove** the filesystem object is the same. This step never
moves a file, searches directories, retries scanning, opens a file, changes
preferences, or grants permissions. The sensitive path must remain in the
trusted extension-to-native boundary; never log, persist, or forward it to
untrusted webpages.

**Limit:** External filesystem moves may not update browser download
metadata. Browser-provided `exists`, `filename`, transfer counters, and
download IDs are not canonical file identity evidence. A separately reviewed
trusted native coordinator is still required to safely resolve physical
relocation, verify the canonical path and file identity/stability **at scan
dispatch**, and enforce the existing ClamAV freshness, full-byte scan,
quarantine, integrity and selected-application opening protections. This
module cannot independently discover arbitrary external moves and never
claims otherwise.

The existing `npm test` / required `scanner-tests` CI step executes
`tests/download-postmove.test.mjs`, covering post-completion relocation,
deleted/unfinished files, stale records, permission revocation, malformed
snapshots, adversarial accessors and no import-time behavior.
