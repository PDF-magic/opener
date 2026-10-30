# Extensions source

This directory is reserved for PDF Magic Opener extension source
(implementation checklist §9.1). Git tracks files rather than empty
directories, so this source-only scaffold started with opener-0559.

The shared, dependency-free WebExtensions project now lives at
[`webextension/`](webextension/README.md) (opener-0560). Its local build
produces only a permission-free, non-operational browser manifest. This is
**not an enabled or functional PDF-processing extension**. A separately
sandboxed Safari Web Extension target now packages the permission-free manifest
inside the native app (opener-0567); it does not auto-enable the extension,
request website access, scan or open PDFs, or modify preferences.
See [`safari/`](safari/README.md) for the target and packaging boundary.

Future extensions must be reviewed and wired separately while preserving
mandatory ClamAV scanning, signature freshness, file-integrity and quarantine
checks, and the user-selected application preferences.
