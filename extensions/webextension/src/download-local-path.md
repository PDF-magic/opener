# Absolute local download path lookup (opener-0677)

`retrieveCompletedDownloadLocalPath(downloadsApi, permissionsApi, completion)`
returns a Promise of a frozen `{ id, localPath }` or `null`. A completed
browser download's `filename` can contain an absolute filesystem path, but
it can also be absent or not an absolute path. This wrapper distinguishes
those cases without duplicating the completed-ID browser query.

The implementation delegates to the already-merged
`retrieveCompletedDownloadFilename` helper (opener-0676 / PR #446). That
helper validates the exact `{kind: "completed", id}` notice, subscribes
to permission revocations before verifying the **current** optional
`downloads` grant, performs only `downloads.search({id})`, and requires
exactly one matching record with `state: "complete"`. Failed grants, removed
permission, missing results, malformed metadata and browser errors return
`null` without logging sensitive details.

A `localPath` is returned only for a bounded, nonempty **syntactically
absolute** POSIX path (for example `/Users/alice/Downloads/report.pdf`) or
a Windows drive-absolute path (for example `C:\Users\Alice\Downloads\report.pdf`).
Relative paths, URI strings, Windows device/UNC paths, root-only values,
ambiguous/repeated separators, traversal components and Windows alternate
data stream suffixes are rejected. The underlying filename helper already
rejects control characters, malformed records and excessive lengths.

**Path availability is not proof of file existence, canonicalization, file
ownership or identity, PDF content, safe scanner output, or permission to open
a file.** Even a path from the browser must be independently validated by
a separately reviewed trusted native coordinator before any scanning or
handoff. Never log, persist, broadcast to webpages, or send this path in a
native message. File-integrity controls, ClamAV freshness, full scan,
quarantine, and the user's selected PDF application remain authoritative.

No filesystem read, permission request, scanner invocation, download
subscription, background activation, or user preference mutation occurs.
The new `tests/download-local-path.test.mjs` runs automatically in the
existing WebExtensions `npm test` CI command. Tests cover absolute and
unavailable local paths, invalid IDs, browser errors, permission-denied and
revocation races, privacy, and inert module behavior.
