# Permission-checked download-created event registration (opener-0671)

`registerDownloadCreatedEvents(downloadsApi, permissionsApi, onCreated,
{ monitoringEnabled: true, onError? })` is an **explicit** activation helper
for WebExtensions `downloads.onCreated`. It registers **only** this event,
not `onChanged` or `onErased`, and returns a Promise resolving to an
idempotent teardown function. The module has no import-time effects.

The caller must already have received the user's express choice to enable
monitoring; this helper does not grant consent or prove a user gesture. Before
attaching the listener, it checks an actual browser
`permissions.contains({ permissions: ["downloads"] })` Promise and requires
exactly `true`. It never calls `permissions.request`. Unsupported APIs,
denied or uncertain permission, missing permission-revocation support, and
listener failures all fail closed. A download permission removal **immediately**
disables and detaches monitoring; removal while permission verification or
listener registration is pending cannot reactivate it. Explicit opt-in and
current permission verification are required again to reenable monitoring.

Every delivered event uses the existing normalized, immutable, allowlisted
`normalizeDownloadEvent("created", item)` record. Browser URLs, referrers,
cookies, headers, and file bytes are never forwarded. Filename, MIME, state,
and danger are **untrusted browser metadata**, never a scanner verdict.
Consumer failures are isolated with a generic path-free error. No history,
downloads.search, downloads.open, PDF reads, native messaging, or network calls
are performed.

The shipped Chromium/Firefox/Safari extension backgrounds remain **inactive**.
The repo does not yet have a reviewed settings-loading and user-consent UI
binding that can call this helper with effective opt-in state, so actual
monitoring must not start automatically during startup or installation.
Wiring the browser background into that UI is a separate prerequisite, not
silently introduced under this checklist item.

The opt-in `downloads` permission remains optional; the extension's required
permissions and host permissions are unchanged. The native scanner's ClamAV
freshness, integrity, quarantine, verified-open and user-selected PDF
application gates are untouched. The existing `scanner-tests` GitHub Actions
job runs `npm test`, automatically executing
`tests/download-created-events.test.mjs` with permission, lifecycle, privacy,
reentrancy, and denial regressions.
