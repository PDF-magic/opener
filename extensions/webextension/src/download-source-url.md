# Retrieve a browser download's source URL (opener-0679)

`retrieveDownloadSourceUrl(downloadsApi, permissionsApi, notice)` is an
**explicit, one-shot, ID-scoped** browser metadata lookup. It accepts either a
normalized `{ kind: "created", id, ... }` download-created event or a frozen
`{ kind: "completed", id }` completion notice. It calls only
`downloads.search({ id })`, never scans browser download history, fetches
the URL, inspects download bytes, or opens a file. An absent source URL returns
`null`. A final redirect URL (`finalUrl`) or referrer is **not** substituted
for the original `url` field.

The caller must independently verify the user's explicit opt-in to download
monitoring. This helper then independently checks the **current** optional
`downloads` permission with `permissions.contains` and watches for
`permissions.onRemoved` **before** the asynchronous permission check and
throughout the download search. Any denial, unsupported API, ambiguous or
mismatched ID, interruption, invalid response, or intervening permission
revocation fails closed with `null`. Only promise-based permission and search
APIs with an affirmative current grant are accepted. All browser errors are
swallowed without printing potentially sensitive URL strings.

Only the browser's `url` (source URL) is returned in a frozen `{ id, url }`
record, and only when it is an absolute HTTP(S) URL. URLs containing embedded
credentials, raw control characters/whitespace, an invalid hostname, malformed
syntax, or more than 8192 characters are rejected. `file:`, `blob:`,
`data:`, `javascript:`, and other non-network schemes are never exposed.
A created notice permits an in-progress or completed entry; a completed
notice requires the entry's browser state to still be exactly `complete`.
No local file path, final redirect URL, cookies, request headers, referrers,
danger status, MIME declaration, or scanner verdict is returned.

**Privacy boundary:** source URLs may contain sensitive paths and query tokens.
They are returned solely to the explicitly invoking, trusted extension
component. They are intentionally **not added** to the generic event
normalizer, the default download-created event callback, logs, settings,
browser telemetry, native scan requests, or persistence. A future integration
must separately justify any use, display, retention, or disclosure. The
installed background remains inert; this change requests no browser
permissions and does not enable download monitoring automatically.

Source URL metadata does **not** establish that a file is safe, identify a
PDF, authorize native file access, bypass ClamAV freshness, integrity,
quarantine, verified-open rules, or change the selected PDF application.
Existing user customizations remain untouched.

`tests/download-source-url.test.mjs` is discovered by the existing
WebExtensions `npm test` command in `scanner-tests` CI. Tests cover real
created/completed adapters, strict ID matching, grant and revocation races,
missing URL handling, scheme and credential rejection, hostile browser
getters, and inactive background/native safety boundaries.
