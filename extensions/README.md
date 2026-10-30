# Extensions source

This directory is reserved for PDF Magic Opener extension source
(implementation checklist §9.1). Git tracks files rather than empty
directories, so this source-only scaffold started with opener-0559.

The shared, dependency-free WebExtensions project now lives at
[`webextension/`](webextension/README.md) (opener-0560). Its local build
produces only a permission-free, non-operational browser manifest. This is
**not an installed or enabled extension** or a native app extension target;
it adds no privileged entitlement, launch handler, scanner bypass or
integration.

Future extensions must be reviewed and wired separately while preserving
mandatory ClamAV scanning, signature freshness, file-integrity and quarantine
checks, and the user-selected application preferences.
