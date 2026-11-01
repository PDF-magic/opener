# Extensions source

This directory is reserved for PDF Magic Opener extension source
(implementation checklist §9.1). Git tracks files rather than empty
directories, so this source-only scaffold started with opener-0559.

The shared, dependency-free WebExtensions project now lives at
[`webextension/`](webextension/README.md) (opener-0560). Its local build
produces an inactive Chromium/Firefox manifest with no required API or site
permissions. The shared source project is **not an installed or enabled extension**
and is not a functional PDF processor. A separately sandboxed
Safari Web Extension target packages a Safari-specific manifest with the
required `nativeMessaging` declaration inside the native app (opener-0567);
it does not auto-enable the extension, request website access, scan or open
PDFs, or modify preferences. See [`safari/`](safari/README.md) for the target
and packaging boundary.

See [browser extension permission requirements](../docs/browser-extension-permissions.md)
for the browser-by-browser matrix, optional-download consent, Safari's
native-messaging distinction, and permissions that are not currently needed.

Future extensions must be reviewed and wired separately while preserving
mandatory ClamAV scanning, signature freshness, file-integrity and quarantine
checks, and the user-selected application preferences.
