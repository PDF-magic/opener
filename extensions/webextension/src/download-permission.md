# Optional download monitoring permission (opener-0583)

The shared Manifest V3 source, Chromium build and Firefox build declare
`optional_permissions: ["downloads"]`. They retain `permissions: []` and
`host_permissions: []`, without optional host access. This **declares an
optional capability**, not an install-time grant. Neither `downloads.open`,
`tabs`, `nativeMessaging`, site access nor file access is requested.

`requestDownloadMonitoringPermission(permissionsApi, {
  monitoringEnabled: true, userInitiated: true
})` is the only API added in this task. It passes the fixed
`{ permissions: ["downloads"] }` directly to the injected WebExtensions
`permissions.request` method. Both flags must be explicitly true. The
permission request is initiated synchronously inside the function, before
the first asynchronous boundary, so a separately reviewed future UI can
call it directly from a genuine user gesture. **A boolean flag alone is not
proof of a gesture or authorization.** The UI integration remains future work.

Importing the module, extension installation/startup, opening the toolbar
and the existing default-off configuration **do not ask for permission**.
Denial, exceptions, Promise rejection, missing support and callback-only
implementations all return `false` (no inferred grant). Only the exact
boolean `true` response is accepted. No permission is persisted or revoked
by this helper: existing user choices must not be overwritten.

The helper does not register monitoring listeners; the existing passive
`download-monitoring.js` adapter remains unconnected to the inert background.
A future reviewed activation task must check the returned grant and
explicitly start/stop the listener, handle permission revocation and preserve
user consent. Safari support for optional runtime grants must be validated
before any real UI is enabled; unsupported browsers fail closed.

The user-selected native PDF destination and all ClamAV freshness, quarantine,
file-integrity and verified-open safeguards remain unchanged. Permission to
observe browser download events is **not** a malware-clean verdict or
authorization to open files.
