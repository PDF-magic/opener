# Shared extension configuration defaults (opener-0574)

`src/configuration-defaults.js` declares the versioned, immutable
`DEFAULT_EXTENSION_CONFIG` baseline for the future WebExtensions integration.
`createDefaultExtensionConfig()` returns a fresh copy so no caller can mutate
the baseline or another caller's settings. Current version: `1`.

| Setting | Default | Purpose |
| --- | --- | --- |
| `downloadMonitoringEnabled` | `false` | Do not register download monitoring automatically |
| `automaticScanRequestsEnabled` | `false` | Do not submit automatic download scan requests |
| `nativeMessagingEnabled` | `false` | Do not connect to a native messaging host automatically |
| `automaticOpenEnabled` | `false` | Do not launch PDFs automatically |
| `notificationsEnabled` | `false` | Do not show unsolicited extension notifications |

These are **configuration defaults only**, not a working extension workflow.
They do not grant browser permissions, request file access, enable a native
connection, classify an item as safe or bypass the installed app's ClamAV
signature freshness, file-integrity, quarantine, or user-selected destination
checks. The existing permission-free manifest and scanner are unchanged.

**No existing user settings are read, migrated, overwritten, or reset.**
Loading, validation, preference persistence and user-controlled opt-in
belong to separately reviewed tasks. In particular, importing this module
does not write to `browser.storage`, register background listeners, or
activate download monitoring. Do not treat a missing stored preference as
consent for an automatic action.

CI discovers `tests/configuration-defaults.test.mjs` through the existing
WebExtensions `npm test` command inside the repository's `scanner-tests`
workflow. Tests enforce safe defaults, immutability, fresh copies, unchanged
browser permissions and the absence of storage/browser/native side effects.
